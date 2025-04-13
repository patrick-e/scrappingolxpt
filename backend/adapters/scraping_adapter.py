import random
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException

from ..domain.ports.scraping_service import ScrapingServicePort
from ..domain.entities.scraping import ScrapingData
from ..config.credentials import CredentialsManager

def fetch_random_proxies() -> list[str]:
    """Busca e testa proxies de múltiplas fontes de forma paralela."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    proxy_apis = [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=1000&country=all&ssl=all&anonymity=all",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt"
    ]
    
    def fetch_from_api(api):
        try:
            response = requests.get(api, timeout=5)
            if response.status_code == 200:
                return set(response.text.splitlines())
        except Exception as e:
            print(f"[PROXY] Erro ao buscar proxies de {api}: {str(e)}")
        return set()

    def test_proxies_batch(proxies):
        working = []
        for proxy in proxies:
            if test_proxy(proxy, timeout=3):  # Reduzido timeout para 3 segundos
                working.append(proxy)
                if len(working) >= 2:  # Limite por batch
                    break
        return working

    # Buscar proxies em paralelo
    all_proxies = set()
    with ThreadPoolExecutor(max_workers=3) as executor:
        api_futures = {executor.submit(fetch_from_api, api): api for api in proxy_apis}
        for future in as_completed(api_futures):
            all_proxies.update(future.result())

    if not all_proxies:
        return []

    # Testar proxies em paralelo
    working_proxies = []
    proxy_batches = [list(all_proxies)[i:i+5] for i in range(0, min(len(all_proxies), 25), 5)]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        test_futures = {executor.submit(test_proxies_batch, batch): batch for batch in proxy_batches}
        for future in as_completed(test_futures):
            working_proxies.extend(future.result())
            if len(working_proxies) >= 10:
                break

    random.shuffle(working_proxies)
    return working_proxies[:10]

def test_proxy(proxy: str, timeout: int = 5) -> bool:
    """Testa se um proxy está funcionando."""
    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
    try:
        response = requests.get("https://www.google.com", proxies=proxies, timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False

def rotate_proxy(proxies: list[str], current_proxy: str) -> str:
    """Seleciona um novo proxy diferente do atual."""
    if not proxies:
        return None
    available_proxies = [p for p in proxies if p != current_proxy]
    return random.choice(available_proxies) if available_proxies else proxies[0]

class BeautifulSoupAdapter(ScrapingServicePort):
    def __init__(self, email=None, password=None, proxies=None):
        """Inicializa o adaptador com suporte a proxy rotativo."""
        self.proxies = proxies or []
        self.current_proxy = None
        self.driver = None
        self.email = email
        self.password = password
        self.retry_count = 3
        self.timeout = 30  # Aumentado para 30 segundos
        self.session_valid = False
        self.last_request = 0
        self.min_request_delay = 1.0  # Delay mínimo entre requisições
        print("[SCRAPING] Adaptador inicializado com sucesso")

    def _respect_rate_limit(self):
        """Garante um intervalo mínimo entre requisições."""
        now = time.time()
        time_since_last = now - self.last_request
        if time_since_last < self.min_request_delay:
            time.sleep(self.min_request_delay - time_since_last)
        self.last_request = time.time()

    def _get_chrome_options(self) -> webdriver.ChromeOptions:
        """Retorna as opções do Chrome organizadas por categoria."""
        options = webdriver.ChromeOptions()
        
        # Define as configurações por categoria
        chrome_prefs = {
            'performance': {
                'disable-gpu': False,
                'no-sandbox': True,
                'disable-dev-shm-usage': True,
                'disable-blink-features': 'AutomationControlled'
            },
            'security': {
                'disable-web-security': True,
                'ignore-certificate-errors': True
            },
            'features': {
                'disable-extensions': True,
                'disable-notifications': True,
                'disable-infobars': True,
                'disable-features': 'TranslateUI,AutomationControlled'
            },
            'privacy': {
                'enable-do-not-track': False,
                'disable-sync': True
            },
            'cache': {
                'disk-cache-size': 32768,
                'media-cache-size': 32768,
                'aggressive-cache-discard': True,
                'disable-cache': True,
                'disable-application-cache': True,
                'disable-offline-load-stale-cache': True
            },
            'rendering': {
                'disable-software-rasterizer': True,
                'enable-gpu-rasterization': True
            }
        }
        
        # Configurações para evitar timeouts
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-background-networking')
        
        # Configurações para melhorar performance
        prefs = {
            'profile.default_content_setting_values.notifications': 2,
            'profile.default_content_settings.popups': 0,
            'profile.password_manager_enabled': False,
            'credentials_enable_service': False,
            'webrtc.ip_handling_policy': 'disable_non_proxied_udp',
            'disk-cache-size': 53687091200,  # 50 GB
            'profile.managed_default_content_settings.images': 1,
            'profile.managed_default_content_settings.javascript': 1
        }
        options.add_experimental_option('prefs', prefs)
        
        # Aplica as configurações de forma organizada
        for category, settings in chrome_prefs.items():
            for setting, value in settings.items():
                if isinstance(value, bool) and value:
                    options.add_argument(f'--{setting}')
                elif isinstance(value, (int, str)):
                    options.add_argument(f'--{setting}={value}')
                    
        # Configurações anti-detecção
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        return options
        
    def _initialize_browser(self):
        """Inicializa o navegador com configurações otimizadas e proxy."""
        if self.driver:
            self._cleanup_driver()

        options = self._get_chrome_options()
        
        # Configurações de proxy
        if self.current_proxy:
            options.add_argument(f'--proxy-server={self.current_proxy}')
            print(f"[PROXY] Configurando proxy: {self.current_proxy}")
        
        # Configuração de timeout e espera
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)  # Aumentado para 30 segundos
            self.driver.implicitly_wait(10)  # Aumentado para 10 segundos
            
            # Definir tamanho da janela para desktop
            self.driver.set_window_size(1920, 1080)
            print("[BROWSER] Navegador inicializado com sucesso")
            
        except Exception as e:
            print(f"[BROWSER] Erro ao inicializar navegador: {str(e)}")
            self._cleanup_driver()
            raise

    def _accept_cookies(self, wait: WebDriverWait = None) -> bool:
        """Aceita os cookies se o botão estiver presente. Retorna True se conseguiu aceitar."""
        try:
            if wait is None:
                wait = WebDriverWait(self.driver, 15)  # Aumentado timeout para 15 segundos
            
            # Aguardar a página carregar completamente
            time.sleep(random.uniform(2.0, 3.0))
            
            # Lista de possíveis seletores para o botão de cookies (em ordem de prioridade)
            cookie_selectors = [
                '#onetrust-accept-btn-handler',  # OneTrust
                'button[data-testid="cookie-policy-dialog-accept-button"]',  # OLX padrão
                'button.fc-button-accept-all',  # CookieBot
                'button[data-testid="button.accept"]',  # Variação OLX
                'button.css-47sehv',  # OLX específico
                'button[aria-label="Aceitar todos os cookies"]',  # Genérico PT
                'button[data-role="accept-consent"]',  # Alternativo
                'button.fc-cta-consent'  # Fallback
            ]
            
            # Tentar cada seletor
            for selector in cookie_selectors:
                try:
                    print(f"[COOKIES] Tentando seletor: {selector}")
                    
                    # Esperar o botão estar presente e visível
                    cookie_button = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    
                    # Rolar até o botão
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", cookie_button)
                    time.sleep(random.uniform(0.5, 1.0))
                    
                    # Esperar ser clicável
                    cookie_button = wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    
                    # Tentar diferentes métodos de clique
                    try:
                        cookie_button.click()
                    except:
                        try:
                            self.driver.execute_script("arguments[0].click();", cookie_button)
                        except:
                            actions = ActionChains(self.driver)
                            actions.move_to_element(cookie_button).pause(0.5).click().perform()
                    
                    print(f"[COOKIES] Cookies aceitos com sucesso usando seletor: {selector}")
                    time.sleep(1)  # Aguardar efeito do clique
                    return True
                    
                except Exception as e:
                    print(f"[COOKIES] Falha ao tentar seletor {selector}: {str(e)}")
                    continue
            
            print("[COOKIES] Nenhum seletor de cookie funcionou")
            return False
            
        except Exception as e:
            print(f"[COOKIES] Erro ao tentar aceitar cookies: {str(e)}")
            return False
            
    def login(self, progress_callback=None) -> bool:
        """Realiza login no site com tratamento robusto de cookies."""
        try:
            if progress_callback:
                progress_callback(0, "Iniciando processo de login...")

            if not self.email or not self.password:
                raise ValueError("Email e senha são obrigatórios")

            self._initialize_browser()
            self.driver.get("https://www.olx.pt")
            
            # Configurar timeouts para garantir máximo de 35 segundos por página
            wait = WebDriverWait(self.driver, 10)  # Reduzido para 10 segundos
            self.driver.set_page_load_timeout(15)  # 15 segundos para carregar página
            print("[LOGIN] Configurando timeouts - Page load: 15s, Element wait: 10s")
            
            # Aguardar página carregar (máximo 2 segundos)
            time.sleep(random.uniform(1.0, 2.0))
            
            # Primeiro tentar aceitar os cookies
            max_cookie_attempts = 3
            cookies_accepted = False
            
            for attempt in range(max_cookie_attempts):
                if progress_callback:
                    progress_callback(10, f"Tentando aceitar cookies (tentativa {attempt + 1})...")
                
                if self._accept_cookies(wait):
                    cookies_accepted = True
                    print("[LOGIN] Cookies aceitos com sucesso")
                    if progress_callback:
                        progress_callback(15, "Cookies aceitos, aguardando estabilização...")
                    break
                    
                time.sleep(2)  # Aguardar entre tentativas
            
            if not cookies_accepted:
                print("[LOGIN] Aviso: Não foi possível aceitar os cookies após várias tentativas")
                if progress_callback:
                    progress_callback(15, "Continuando mesmo sem aceitar cookies...")
                
            # Aguardar página estabilizar após cookies (máximo 1 segundo)
            time.sleep(random.uniform(0.5, 1.0))
            
            if progress_callback:
                progress_callback(20, "Procurando botão de login...")
                
            # Esperar página carregar antes de tentar login (máximo 1.5 segundos)
            time.sleep(random.uniform(1.0, 1.5))
            
            # Tentar diferentes seletores para o botão de login
            login_button_selectors = [
                'a[data-cy="myolx-link"]',  # Seletor principal da OLX PT
                'div.css-zs6l2q a',  # Container + link
                'a[href*="/account/"]',  # Link parcial
                'a:has(svg)',  # Link com ícone SVG
                '.css-12l1k7f',  # Classe específica do link
                'a:contains("A tua conta")',  # Texto do link
                # Fallbacks anteriores
                'button[data-testid="myaccount-link"]',
                'button[data-cy="myaccount-link"]',
                'a[href*="login"]'
            ]
            
            login_button_found = False
            max_login_attempts = 3
            
            for attempt in range(max_login_attempts):
                if login_button_found:
                    break
                    
                print(f"[LOGIN] Tentativa {attempt + 1} de encontrar botão de login...")
                
                for selector in login_button_selectors:
                    try:
                        print(f"[LOGIN] Tentando localizar botão com seletor: {selector}")
                        
                        # Tentar encontrar o botão com diferentes métodos
                        try:
                            login_trigger = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                        except:
                            # Tentar com XPath para texto específico
                            try:
                                login_trigger = wait.until(EC.presence_of_element_located(
                                    (By.XPATH, "//a[contains(., 'A tua conta')]")
                                ))
                            except:
                                continue
                        
                        # Garantir que está visível
                        if not login_trigger.is_displayed():
                            print("[LOGIN] Elemento encontrado mas não visível, tentando scroll...")
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", login_trigger)
                            time.sleep(random.uniform(0.5, 1.0))
                        
                        # Tentar diferentes métodos de clique
                        click_methods = [
                            # Método 1: Clique direto
                            lambda: login_trigger.click(),
                            
                            # Método 2: Clique via JavaScript
                            lambda: self.driver.execute_script("arguments[0].click();", login_trigger),
                            
                            # Método 3: Navegar direto para o href
                            lambda: self.driver.execute_script("""
                                var href = arguments[0].getAttribute('href');
                                if (href) window.location.href = href;
                            """, login_trigger),
                            
                            # Método 4: Action Chains com movimentos naturais
                            lambda: ActionChains(self.driver)
                                .move_to_element(login_trigger)
                                .pause(random.uniform(0.3, 0.5))
                                .click()
                                .perform()
                        ]
                        
                        click_success = False
                        for click_method in click_methods:
                            try:
                                print("[LOGIN] Tentando método de clique alternativo...")
                                click_method()
                                time.sleep(1)  # Pequena espera para ver se houve efeito
                                
                                # Verificar se chegamos à página de login ou se o modal apareceu
                                try:
                                    # Lista de possíveis seletores para o formulário de login
                                    form_selectors = [
                                        'div[data-testid="login-dialog"]',  # Modal padrão
                                        'form#loginForm',                   # Form direto
                                        'div.login-box',                    # Container alternativo
                                        'div[data-testid="login-form"]'     # Form dentro do modal
                                    ]
                                    
                                    form_found = False
                                    for form_selector in form_selectors:
                                        try:
                                            print(f"[LOGIN] Verificando formulário: {form_selector}")
                                            form = wait.until(EC.presence_of_element_located(
                                                (By.CSS_SELECTOR, form_selector)
                                            ))
                                            
                                            if form.is_displayed():
                                                # Verificar se os campos necessários estão presentes
                                                email_field = form.find_element(By.CSS_SELECTOR,
                                                    'input[type="email"], input[name="email"], input[data-testid="email-input"]'
                                                )
                                                password_field = form.find_element(By.CSS_SELECTOR,
                                                    'input[type="password"], input[name="password"], input[data-testid="password-input"]'
                                                )
                                                
                                                if email_field.is_displayed() and password_field.is_displayed():
                                                    form_found = True
                                                    print(f"[LOGIN] Formulário válido encontrado com seletor: {form_selector}")
                                                    break
                                        except Exception as e:
                                            print(f"[LOGIN] Erro ao verificar formulário {form_selector}: {str(e)}")
                                            continue
                                    
                                    if form_found:
                                        click_success = True
                                        login_button_found = True
                                        print("[LOGIN] Login form encontrado e validado")
                                        break
                                    
                                except Exception as e:
                                    print(f"[LOGIN] Erro ao verificar formulários: {str(e)}")
                                    continue
                                    
                            except Exception as e:
                                print(f"[LOGIN] Método de clique falhou: {str(e)}")
                                continue
                        
                        if not click_success:
                            print("[LOGIN] Todos os métodos de clique falharam")
                            continue
                            
                    except Exception as e:
                        print(f"[LOGIN] Falha ao tentar seletor {selector}: {str(e)}")
                        continue
                
                if not login_button_found:
                    if attempt < max_login_attempts - 1:
                        print("[LOGIN] Recarregando página para nova tentativa...")
                        self.driver.refresh()
                        time.sleep(random.uniform(2.0, 3.0))
                        # Aceitar cookies novamente após refresh
                        cookies_success = self._accept_cookies(wait)
                        print(f"[LOGIN] Cookies após refresh: {'aceitos' if cookies_success else 'falha ao aceitar'}")
                        continue
                    else:
                        raise Exception("Não foi possível encontrar ou clicar no botão de login após múltiplas tentativas")
            
            # Preencher campos de login com delays naturais
            if progress_callback:
                progress_callback(40, "Procurando campos de login...")
                
            # Tentar diferentes seletores para campos de login
            email_selectors = [
                'input[data-testid="email-input"]',
                'input[type="email"]',
                'input[name="email"]',
                'input#email'
            ]
            
            password_selectors = [
                'input[data-testid="password-input"]',
                'input[type="password"]',
                'input[name="password"]',
                'input#password'
            ]
            
            # Encontrar campo de email
            email_field = None
            for selector in email_selectors:
                try:
                    email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    if email_field.is_displayed():
                        print(f"[LOGIN] Campo de email encontrado: {selector}")
                        break
                except:
                    continue
                    if not email_field:
                        raise Exception("Não foi possível encontrar o campo de email")
                        
                    # Encontrar campo de senha
                    password_field = None
                    for selector in password_selectors:
                        try:
                            password_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                            if password_field.is_displayed():
                                print(f"[LOGIN] Campo de senha encontrado: {selector}")
                                break
                        except:
                            continue
                            
                    if not password_field:
                        raise Exception("Não foi possível encontrar o campo de senha")
                    
                    if progress_callback:
                        progress_callback(50, "Preenchendo credenciais...")
                    
                    # Preencher campos com delays naturais
                    print("[LOGIN] Preenchendo email...")
                    for char in self.email:
                        email_field.send_keys(char)
                        time.sleep(random.uniform(0.1, 0.2))
                    
                    time.sleep(random.uniform(0.5, 1.0))
                    
                    print("[LOGIN] Preenchendo senha...")
                    for char in self.password:
                        password_field.send_keys(char)
                        time.sleep(random.uniform(0.1, 0.2))
                    
                    time.sleep(random.uniform(0.5, 1.0))
                    
                    if progress_callback:
                        progress_callback(60, "Procurando botão de submit...")
                    
                    # Tentar diferentes seletores para o botão de submit
                    submit_selectors = [
                        'button[data-testid="login-submit-button"]',
                        'button[type="submit"]',
                        'input[type="submit"]',
                        'button.submit-button',
                        'button:contains("Entrar")',
                        'button:contains("Login")'
                    ]
                    
                    # Tentar clicar no botão de submit
                    submit_success = False
                    for selector in submit_selectors:
                        try:
                            submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                            print(f"[LOGIN] Botão de submit encontrado: {selector}")
                            
                            # Tentar diferentes métodos de clique
                            click_methods = [
                                lambda: submit_button.click(),
                                lambda: self.driver.execute_script("arguments[0].click();", submit_button),
                                lambda: ActionChains(self.driver).move_to_element(submit_button).click().perform()
                            ]
                            
                            for click_method in click_methods:
                                try:
                                    click_method()
                                    submit_success = True
                                    print("[LOGIN] Clique no botão de submit bem sucedido")
                                    break
                                except Exception as e:
                                    print(f"[LOGIN] Falha no método de clique: {str(e)}")
                                    continue
                                    
                            if submit_success:
                                break
                                
                        except Exception as e:
                            print(f"[LOGIN] Falha ao tentar seletor de submit {selector}: {str(e)}")
                            continue
                    
                    if not submit_success:
                        raise Exception("Não foi possível clicar no botão de submit do login")
            if not email_field:
                raise Exception("Não foi possível encontrar o campo de email")
            # Preencher email (máximo 1.5 segundos)
            email_field.send_keys(self.email)
            time.sleep(random.uniform(0.3, 0.5))
            
            if progress_callback:
                progress_callback(50, "Email preenchido, inserindo senha...")
            
            # Preencher senha (máximo 1.5 segundos)
            password_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-testid="password-input"]')))
            password_field.send_keys(self.password)
            time.sleep(random.uniform(0.3, 0.5))
            
            if progress_callback:
                progress_callback(60, "Credenciais inseridas, tentando fazer login...")
                
            time.sleep(random.uniform(0.8, 1.2))
            # Tentar submeter o login com retentativas
            submit_success = False
            for attempt in range(max_login_attempts):
                try:
                    print(f"[LOGIN] Tentativa {attempt + 1} de submeter login...")
                    
                    # Esperar botão ficar clicável
                    login_button = wait.until(EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, 'button[data-testid="login-submit-button"]')
                    ))
                    
                    # Tentar diferentes métodos de clique
                    try:
                        login_button.click()
                    except:
                        try:
                            self.driver.execute_script("arguments[0].click();", login_button)
                        except:
                            actions = ActionChains(self.driver)
                            actions.move_to_element(login_button).pause(0.5).click().perform()
                    
                    # Aguardar após o clique (máximo 1.5 segundos)
                    time.sleep(random.uniform(1.0, 1.5))
                    
                    # Verificar se o login foi bem sucedido através de múltiplos indicadores
                    success_indicators = {
                        'logged_link': '[data-testid="myaccount-link-logged"]',
                        'user_menu': '[data-testid="user-menu"]',
                        'profile_icon': '[data-testid="profile-icon"]'
                    }
                    
                    # Usar wait para verificação (máximo 8 segundos)
                    verify_wait = WebDriverWait(self.driver, 8)
                    
                    # Tentar verificar cada indicador
                    for indicator_name, selector in success_indicators.items():
                        try:
                            print(f"[LOGIN] Verificando indicador de login: {indicator_name} ({selector})")
                            start_time = time.time()
                            element = verify_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                            
                            if element.is_displayed():
                                print(f"[LOGIN] Login confirmado através do indicador: {indicator_name} "
                                      f"(tempo decorrido: {time.time() - start_time:.2f}s)")
                                submit_success = True
                                
                                # Registrar estado da página para debug
                                print("[LOGIN] Estado atual da página:")
                                print(f"- URL: {self.driver.current_url}")
                                print(f"- Título: {self.driver.title}")
                                
                                break
                        except Exception as e:
                            print(f"[LOGIN] Indicador {indicator_name} não encontrado: {str(e)}")
                            continue
                    
                    if submit_success:
                        print("[LOGIN] Login realizado com sucesso!")
                        break
                        
                except Exception as e:
                    print(f"[LOGIN] Erro ao tentar submeter login (tentativa {attempt + 1}): {str(e)}")
                    if attempt < max_login_attempts - 1:
                        time.sleep(2)
                        continue
            
            if not submit_success:
                raise Exception("Não foi possível confirmar o login após múltiplas tentativas")
            
            print("[LOGIN] Login realizado e verificado com sucesso")
            if progress_callback:
                progress_callback(100, "Login realizado com sucesso!")
            
            return True
            
        except Exception as e:
            print(f"[LOGIN] Erro ao realizar login: {str(e)}")
            if progress_callback:
                progress_callback(0, "Falha ao realizar login")
            return False

    def extract_data(self, url: str, progress_callback=None) -> ScrapingData:
        """Extrai dados da URL fornecida com retry e tratamento de erros otimizado."""
        try:
            self._init_proxies(progress_callback)
            
            # Primeiro extrai a lista de itens usando BeautifulSoup (sem login)
            items_data = self._extract_items_list(url, progress_callback)
            
            # Se falhar com o proxy atual, tenta com outro
            for attempt in range(self.retry_count):
                try:
                    # Processa os detalhes usando Selenium (requer login)
                    detailed_data = self._process_items(items_data, progress_callback)
                    return ScrapingData(url, detailed_data)
                except Exception as e:
                    print(f"[EXTRACT] Erro na tentativa {attempt + 1}: {str(e)}")
                    if attempt < self.retry_count - 1:
                        # Tenta rotacionar o proxy
                        if self.proxies:
                            self.current_proxy = rotate_proxy(self.proxies, self.current_proxy)
                            print(f"[PROXY] Alternando para proxy: {self.current_proxy}")
                            if self.driver:
                                self._cleanup_driver()  # Fecha o driver atual
                                self.driver = None  # Força nova inicialização com novo proxy
                        time.sleep(min(2 * (attempt + 1), 6))  # Backoff exponencial limitado
                    else:
                        raise Exception("Falha na extração de dados após todas as tentativas")
        except Exception as e:
            print(f"[EXTRACT] Erro crítico: {str(e)}")
            raise

    def _init_proxies(self, progress_callback=None):
        """Inicializa os proxies se necessário."""
        if progress_callback:
            progress_callback(0, "Iniciando extração de dados...")

        if not self.proxies:
            if progress_callback:
                progress_callback(10, "Buscando proxies disponíveis...")
            self.proxies = fetch_random_proxies()
            if self.proxies:
                self.current_proxy = rotate_proxy(self.proxies, None)
                print(f"[PROXY] Usando proxy inicial: {self.current_proxy}")

    def _attempt_extraction(self, url: str, attempt: int, progress_callback=None) -> dict:
        """Tenta extrair dados de uma URL específica."""
        if not self.driver:
            if progress_callback:
                progress_callback(15, "Inicializando navegador...")
            self._initialize_browser()

        print(f"[SCRAPING] Tentativa {attempt + 1}/{self.retry_count} - URL: {url}")
        if progress_callback:
            progress_callback(20, f"Acessando página... (Tentativa {attempt + 1})")

        self.driver.set_page_load_timeout(10)
        self.driver.get(url)

        if progress_callback:
            progress_callback(50, "Extraindo dados da página...")

        wait = WebDriverWait(self.driver, 5)
        data = self._extract_elements(url, wait)
        
        if progress_callback:
            progress_callback(100, "Extração concluída com sucesso!")
            
        return data

    def _check_login(self) -> bool:
        """Verifica se ainda está logado."""
        try:
            return bool(self.driver.find_element(By.CSS_SELECTOR, '[data-testid="myaccount-link-logged"]'))
        except NoSuchElementException:
            return False

    def _extract_items_list(self, url: str, progress_callback=None) -> list:
        """Extrai lista de itens da página usando BeautifulSoup com suporte a paginação."""
        all_items = []
        current_page = 1
        has_next = True
        session = requests.Session()
        
        while has_next and current_page <= 50:  # Limite de 50 páginas
            self._respect_rate_limit()
            page_url = f"{url}?page={current_page}" if current_page > 1 else url
            response = session.get(page_url)
            
            if progress_callback:
                progress_callback(30, f"Extraindo itens da página {current_page}...")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            items = []
            
            # Seletores possíveis para diferentes estruturas de página
            selectors = {
                'container': [
                    'div[data-testid="listing-grid"] > div[data-testid="listing-card"]',
                    'div[data-cy="l-card"]',
                    'div.css-1sw7q4x'
                ],
                'link': [
                    'a[data-testid="listing-link"]',
                    'a[data-cy="listing-link"]',
                    'a[href*="/d/"]'
                ],
                'name': [
                    'h6[data-testid="ad-title"]',
                    'h6.css-16v5mdi',
                    'div[data-testid="ad-title"] h6'
                ],
                'price': [
                    'span[data-testid="ad-price"]',
                    'p[data-testid="ad-price"]',
                    'span.css-dpj1m8'
                ],
                'seller': [
                    'span[data-testid="seller-name"]',
                    'div[data-testid="seller-name"]',
                    'span.css-1wlgw7s'
                ]
            }
            
            # Tentar cada seletor até encontrar itens
            for container in selectors['container']:
                item_elements = soup.select(container)
                if item_elements:
                    break
                    
            for item_elem in item_elements:
                try:
                    # Encontrar link
                    link = None
                    for link_selector in selectors['link']:
                        link_elem = item_elem.select_one(link_selector)
                        if link_elem and link_elem.has_attr('href'):
                            link = link_elem['href']
                            if not link.startswith('http'):
                                link = f"https://www.olx.pt{link}"  # Base URL específica da OLX Portugal
                            break
                            
                    # Validar se o link é da OLX Portugal
                    if not link or not ('olx.pt' in link):
                        continue
                    
                    if not link:
                        continue
                        
                    # Encontrar outros elementos
                    item_data = {
                        'link': link,
                        'name': 'N/A',
                        'price': 'N/A',
                        'seller_name': 'N/A'
                    }
                    
                    for field, field_selectors in selectors.items():
                        if field == 'container' or field == 'link':
                            continue
                        for selector in field_selectors:
                            elem = item_elem.select_one(selector)
                            if elem:
                                item_data[field] = elem.text.strip()
                                break
                    
                    items.append(item_data)
                    
                except Exception as e:
                    print(f"[EXTRACT] Erro ao extrair item: {str(e)}")
                    continue
            
            all_items.extend(items)
            
            # Verificar próxima página
            next_selectors = [
                'a.next-page:not(.disabled)',
                'a.pagination-next:not(.disabled)',
                'a[rel="next"]'
            ]
            has_next = False
            for selector in next_selectors:
                if soup.select_one(selector):
                    has_next = True
                    break
            
            if not items or not has_next:
                break
                
            current_page += 1
            print(f"[EXTRACT] {len(all_items)} itens encontrados até agora...")
        
        return all_items

    def _process_items(self, items: list, progress_callback=None) -> list:
        """Processa cada item para obter dados detalhados com retry e múltiplos seletores."""
        processed_items = []
        total_items = len(items)
        retry_items = []

        # Inicializa o Selenium e faz login apenas quando for processar os detalhes
        if not self.driver:
            if progress_callback:
                progress_callback(25, "Carregando credenciais para acessar detalhes...")
                
            # Carrega credenciais
            credentials_manager = CredentialsManager()
            credentials = credentials_manager.get_credentials()
            if not credentials:
                raise Exception("Credenciais não encontradas para acessar detalhes dos itens")
                
            self.email = credentials['email']
            self.password = credentials['password']
            
            if progress_callback:
                progress_callback(30, "Iniciando login para acessar detalhes...")
                
            if not self.login(progress_callback):
                raise Exception("Falha ao realizar login para acessar detalhes dos itens")

        phone_selectors = {
            'button': [
                "//button[contains(@data-testid, 'reveal-phone')]",
                "//button[contains(@data-testid, 'show-phone')]",
                "//button[contains(text(), 'Mostrar contacto')]",
                "//button[contains(text(), 'Mostrar número')]"
            ],
            'direct': [
                "//span[contains(@data-testid, 'contact-phone')]",
                "//div[contains(@data-testid, 'seller-phone')]//span",
                "//a[contains(@href, 'tel:')]",
                "//div[contains(@class, 'css-1e7vj83')]//span"  # Classe específica da OLX PT para números
            ]
        }
        
        for idx, item in enumerate(items, 1):
            if progress_callback:
                progress = int(40 + (60 * idx / total_items))
                progress_callback(progress, f"Processando item {idx}/{total_items}...")
            
            try:
                self._respect_rate_limit()
                
                # Tenta acessar a página do item com Selenium para obter o telefone
                self.driver.get(item['link'])
                wait = WebDriverWait(self.driver, 10)  # Aumentado timeout para 10 segundos
                
                # Aguardar página carregar completamente
                time.sleep(random.uniform(2.0, 3.5))  # Delay aleatório mais natural
                
                # Aceitar cookies usando o método dedicado
                self._accept_cookies(wait)
                
                # Aguardar mais um pouco após aceitar cookies
                time.sleep(random.uniform(1.0, 2.0))
                
                # Primeiro tentar botões que revelam o telefone
                phone_found = False
                for button_selector in phone_selectors['button']:
                    try:
                        # Esperar botão ficar visível
                        button = wait.until(EC.presence_of_element_located((By.XPATH, button_selector)))
                        
                        # Rolar até o botão
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                        time.sleep(random.uniform(0.5, 1.0))  # Delay após rolagem
                        
                        # Garantir que o botão está clicável
                        # Simular comportamento humano no clique
                        actions = webdriver.ActionChains(self.driver)
                        actions.move_to_element(button).pause(random.uniform(0.2, 0.5)).click().perform()
                        
                        # Aguardar número aparecer com tempo variável
                        time.sleep(random.uniform(2.0, 3.0))
                        
                        # Tentar pegar o número revelado com múltiplas tentativas
                        max_retries = 3
                        for retry in range(max_retries):
                            if phone_found:
                                break
                                
                            for phone_selector in phone_selectors['direct']:
                                try:
                                    # Esperar explicitamente pelo elemento do telefone
                                    phone_elem = WebDriverWait(self.driver, 5).until(
                                        EC.presence_of_element_located((By.XPATH, phone_selector))
                                    )
                                    phone = phone_elem.text.strip() or phone_elem.get_attribute('href')
                                    
                                    if phone:
                                        # Limpar o número de telefone
                                        if 'tel:' in phone:
                                            phone = phone.split('tel:')[-1]
                                        # Remover caracteres não numéricos exceto +
                                        phone = ''.join(c for c in phone if c.isdigit() or c == '+')
                                        if phone:
                                            item['seller_phone'] = phone
                                            phone_found = True
                                            print(f"[PHONE] Número encontrado: {phone}")
                                            break
                                except Exception as e:
                                    print(f"[PHONE] Tentativa {retry + 1} falhou para seletor {phone_selector}: {str(e)}")
                                    continue
                                    
                            if not phone_found and retry < max_retries - 1:
                                time.sleep(random.uniform(1.0, 2.0))  # Esperar entre tentativas
                                
                        if phone_found:
                            break
                    except:
                        continue
                
                # Se não encontrou por botão, tentar direto
                if not phone_found:
                    for selector in phone_selectors['direct']:
                        try:
                            phone = self._get_element_text(wait, selector)
                            if phone and phone != "N/A":
                                item['seller_phone'] = phone
                                phone_found = True
                                break
                        except:
                            continue
                
                if not phone_found:
                    item['seller_phone'] = "N/A"
                    retry_items.append(item)
                
                processed_items.append(item)
                time.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                print(f"[PROCESS] Erro ao processar item {idx}: {str(e)}")
                item['seller_phone'] = "N/A"
                retry_items.append(item)
                processed_items.append(item)
        
        # Tentar novamente itens que falharam
        if retry_items and len(retry_items) < len(items) * 0.5:  # Se não falharam mais que 50%
            time.sleep(5)  # Espera maior antes de retry
            self.min_request_delay *= 1.5  # Aumenta delay entre requisições
            for item in retry_items:
                try:
                    self._respect_rate_limit()
                    self.driver.get(item['link'])
                    wait = WebDriverWait(self.driver, 8)  # Timeout maior para retry
                    
                    for selector in phone_selectors['direct']:
                        phone = self._get_element_text(wait, selector)
                        if phone and phone != "N/A":
                            idx = processed_items.index(item)
                            processed_items[idx]['seller_phone'] = phone
                            break
                except Exception as e:
                    print(f"[RETRY] Erro no retry do item: {str(e)}")
        
        return processed_items

    def _get_element_text(self, wait: WebDriverWait, xpath: str, attribute=None) -> str:
        """Obtém texto ou atributo de um elemento com tratamento de timeout."""
        try:
            element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            return element.get_attribute(attribute) if attribute else element.text
        except TimeoutException:
            return "N/A"

    def _handle_extraction_error(self, error: Exception, attempt: int, progress_callback=None) -> bool:
        """Lida com erros durante a extração. Retorna False se não deve tentar novamente."""
        print(f"[SCRAPING] Erro na tentativa {attempt + 1}: {str(error)}")
        
        if progress_callback:
            progress_callback(0, f"Erro na tentativa {attempt + 1}, tentando novamente...")

        if self.proxies:
            self.current_proxy = rotate_proxy(self.proxies, self.current_proxy)
            print(f"[PROXY] Rotacionando para novo proxy: {self.current_proxy}")

        self._cleanup_driver()
        time.sleep(min(1 * (attempt + 1), 3))
        
        if attempt >= self.retry_count - 1:
            raise Exception(f"Falha após {self.retry_count} tentativas. Último erro: {str(error)}")
            
        return True

    def transform_data(self, data: ScrapingData) -> list:
        """Transforma e limpa os dados extraídos."""
        print("[TRANSFORM] Iniciando transformação dos dados...")
        
        transformed_items = []
        
        for item in data.data:
            transformed = {}
            
            # Converter valores numéricos e limpar textos
            for key, value in item.items():
                if key == 'price':
                    try:
                        # Remove símbolos monetários e converte para float
                        clean_price = value.replace('€', '').replace('.', '').replace(',', '.').strip()
                        transformed[key] = float(clean_price)
                    except:
                        transformed[key] = value
                elif isinstance(value, str):
                    # Limpa espaços extras e caracteres especiais
                    transformed[key] = ' '.join(value.split())
                else:
                    transformed[key] = value
            
            transformed_items.append(transformed)
        
        print("[TRANSFORM] Dados transformados com sucesso.")
        return transformed_items

    def _cleanup_driver(self):
        """Limpa recursos do driver de forma segura."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"[CLEANUP] Erro ao fechar driver: {str(e)}")
            finally:
                self.driver = None

    def __del__(self):
        """Garante que o driver seja fechado ao destruir o objeto."""
        self._cleanup_driver()
