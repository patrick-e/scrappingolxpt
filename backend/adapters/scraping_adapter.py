import time
import platform
import os
import logging
import random
import requests  # Para buscar proxies de uma API pública
from typing import Tuple
from selenium import webdriver
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.proxy import Proxy, ProxyType
from ..domain.ports.scraping_service import ScrapingServicePort
from ..domain.entities.scraping import ScrapingData
from ..config.credentials import CredentialsManager

def clear_browser_data(driver: webdriver.Chrome) -> None:
    """Limpa dados do navegador para reduzir chance de detecção"""
    try:
        driver.execute_script("""
            window.localStorage.clear();
            window.sessionStorage.clear();
            window.performance.clearResourceTimings();
            window.performance.clearMeasures();
            window.performance.clearMarks();
        """)
        driver.delete_all_cookies()
        print("[BROWSER] Dados do navegador limpos com sucesso")
    except Exception as e:
        print(f"[BROWSER] Erro ao limpar dados: {str(e)}")

def random_wait(min_time: float, max_time: float, reason: str = None) -> None:
    """Aguarda um tempo aleatório entre min_time e max_time segundos"""
    wait_time = random.uniform(min_time, max_time)
    if reason:
        print(f"[TIMING] Aguardando {wait_time:.1f}s - {reason}")
    time.sleep(wait_time)

def get_browser_location():
    """Retorna o caminho do navegador baseado no sistema operacional"""
    system = platform.system().lower()
    if system == "linux":
        return "/usr/bin/brave-browser"
    elif system == "windows":
        # Caminhos comuns do Chrome no Windows
        possible_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
    return None  # Retorna None se nenhum navegador for encontrado

def test_proxy(proxy: str, timeout: int = 5) -> bool:
    """
    Testa se um proxy está funcionando com uma única tentativa.
    """
    try:
        test_url = "https://www.google.com"
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
        response = requests.get(test_url, proxies=proxies, timeout=timeout)
        if response.status_code == 200:
            print(f"[PROXY] Proxy válido: {proxy}")
            return True
        else:
            print(f"[PROXY] Proxy inválido (status {response.status_code}): {proxy}")
            return False
    except Exception as e:
        print(f"[PROXY] Erro ao testar proxy {proxy}: {str(e)}")
        return False

def fetch_random_proxies(api_url: str = "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=1000&country=all&ssl=all&anonymity=all") -> list[str]:
    """
    Busca e testa uma lista de proxies aleatórios de uma API pública.
    """
    try:
        print("[PROXY] Buscando lista de proxies...")
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            all_proxies = response.text.splitlines()
            print(f"[PROXY] {len(all_proxies)} proxies encontrados, testando...")
            
            # Embaralha a lista de proxies para testar em ordem aleatória
            random.shuffle(all_proxies)
            
            working_proxies = []
            max_attempts = min(20, len(all_proxies))  # Testa no máximo 20 proxies
            attempts = 0
            
            for proxy in all_proxies:
                if attempts >= max_attempts:
                    break
                    
                attempts += 1
                print(f"[PROXY] Testando proxy {attempts}/{max_attempts}: {proxy}")
                
                if test_proxy(proxy):
                    print(f"[PROXY] Proxy válido encontrado: {proxy}")
                    working_proxies.append(proxy)
                    if len(working_proxies) >= 5:  # Limita a 5 proxies válidos
                        break
                else:
                    print(f"[PROXY] Proxy inválido: {proxy}")
            
            if working_proxies:
                # Embaralha a lista final de proxies válidos
                random.shuffle(working_proxies)
                print(f"[PROXY] {len(working_proxies)} proxies válidos encontrados:")
                for i, proxy in enumerate(working_proxies, 1):
                    print(f"[PROXY] {i}. {proxy}")
                return working_proxies
            else:
                print("[PROXY] Nenhum proxy válido encontrado após", attempts, "tentativas")
                return []
        else:
            print(f"[PROXY] Falha ao buscar proxies. Código HTTP: {response.status_code}")
            return []
    except Exception as e:
        print(f"[PROXY] Erro ao buscar proxies: {str(e)}")
        return []

def rotate_proxy(proxies: list[str], current_proxy: str) -> str:
    """
    Retorna o próximo proxy da lista ou None se não houver proxies disponíveis.
    """
    if not proxies:
        return None
    
    try:
        current_index = proxies.index(current_proxy)
        next_index = (current_index + 1) % len(proxies)
        return proxies[next_index]
    except ValueError:
        return proxies[0]

class BeautifulSoupAdapter(ScrapingServicePort):
    def __init__(self, email=None, password=None, proxies=None):
        """
        Inicializa o adaptador.
        Se email e senha forem fornecidos, salva as credenciais para uso futuro.
        """
        # Busca proxies aleatórios se não forem fornecidos
        if proxies is None:
            proxies = fetch_random_proxies()
        self.proxies = proxies
        self.current_proxy = None

        # Seleciona um proxy aleatório, se disponível
        if self.proxies:
            self.current_proxy = rotate_proxy(self.proxies, None)
            if self.current_proxy:
                print(f"[PROXY] Usando proxy: {self.current_proxy}")
            else:
                print("[PROXY] Nenhum proxy válido disponível")

        # Variáveis para controle adaptativo de tempos de espera

        # Variáveis para controle adaptativo de tempos de espera
        self.success_count = 0
        self.failure_count = 0
        # Inicializa gerenciador de credenciais
        self.credentials = CredentialsManager()
        
        # Salva novas credenciais se fornecidas
        if email and password:
            print("[INIT] Salvando novas credenciais...")
            self.credentials.save_credentials(email, password)
        # Tempos de espera mais realistas
        self.min_wait_time = 10
        self.max_wait_time = 45
        self.current_wait_time = 20
        
        # Adiciona variação aleatória nos tempos
        self.random_wait_range = (3, 8)
        self.current_wait_time = 15
        
        browser_path = get_browser_location()
        system = platform.system().lower()
        if not browser_path:
            if system == "linux":
                raise Exception("Brave Browser não está instalado. Por favor, instale o Brave Browser para continuar.")
            else:
                raise Exception("Google Chrome não encontrado. Por favor, instale o Google Chrome para continuar.")

        # Configurações do Chrome com perfil mais humano
        options = webdriver.ChromeOptions()
        
        # Headers e configurações básicas
        options.add_argument('--start-maximized')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # User agent realista
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Headers adicionais para parecer mais humano
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-notifications')
        options.add_argument('--lang=pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7')
        
        # Configurações de performance e privacidade
        options.add_argument('--disable-gpu')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--window-size=1920,1080')
        
        # Desabilita indicadores de automação
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        # Configura proxy, se disponível
        if self.current_proxy:
            proxy = Proxy()
            proxy.proxy_type = ProxyType.MANUAL
            proxy.http_proxy = self.current_proxy
            proxy.ssl_proxy = self.current_proxy
            options.proxy = proxy
        
        if system == "linux":
            options.binary_location = browser_path
        
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(self.current_wait_time * 2)
            self.driver.set_script_timeout(self.current_wait_time)
            self.wait = WebDriverWait(self.driver, self.current_wait_time)
            self.short_wait = WebDriverWait(self.driver, max(self.min_wait_time, self.current_wait_time // 2))
        except Exception as e:
            raise Exception(f"Erro ao inicializar o navegador: {str(e)}")

    def _accept_cookies(self):
        """Aceita o banner de cookies se presente"""
        try:
            cookie_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            cookie_button.click()
            time.sleep(1)
            return True
        except (TimeoutException, NoSuchElementException):
            return False

    def _login(self, force_login=False):
        """Realiza login no site"""
        try:
            if not force_login:
                try:
                    print("[SELENIUM] Navegando para página inicial da OLX...")
                    self.driver.get("https://www.olx.pt")
                    
                    # Tempo de espera variável
                    wait_time = random.uniform(8, 12)
                    print(f"[SELENIUM] Aguardando {wait_time:.1f}s para carregamento da página...")
                    time.sleep(wait_time)
                    
                    print("[SELENIUM] Verificando se a página carregou completamente...")
                    self.wait.until(
                        lambda driver: driver.execute_script('return document.readyState') == 'complete'
                    )
                    print("[SELENIUM] Página carregada com sucesso")
                    
                    # Clica no botão "A tua conta"
                    print("[SELENIUM] Procurando botão 'A tua conta'...")
                    account_button = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-cy="myolx-link"]'))
                    )
                    print("[SELENIUM] Botão 'A tua conta' encontrado, clicando...")
                    # Simula comportamento humano ao clicar no botão
                    actions = ActionChains(self.driver)
                    actions.move_to_element(account_button)
                    actions.pause(random.uniform(0.3, 0.7))
                    actions.click()
                    actions.perform()
                    
                    random_wait(2, 4, "após clicar no botão de conta")
                    
                    # Se não redirecionar para login, está logado
                    if "login" not in self.driver.current_url:
                        print("[LOGIN] Já está logado")
                        return True
                except Exception as e:
                    print(f"[LOGIN] Erro ao verificar login: {str(e)}")
                    pass

            print("[LOGIN] Iniciando processo de login...")
            creds = self.credentials.get_credentials()
            print(f"[DEBUG] Tentando carregar credenciais - Sucesso: {bool(creds)}")
            if not creds:
                print("[LOGIN] Credenciais não encontradas")
                # Tenta forçar recarga do .env
                os.environ.clear()
                load_dotenv(override=True)
                creds = self.credentials.get_credentials()
                print(f"[DEBUG] Tentativa de recarga forçada - Sucesso: {bool(creds)}")
                if not creds:
                    print("[LOGIN] Credenciais ainda não encontradas após recarga")
                    return False

            # Força navegação para página de login se necessário
            if "login" not in self.driver.current_url:
                self.driver.get("https://www.olx.pt/account/login/")
            random_wait(2, 4, "após navegar para página de login")

            # Aceita cookies se necessário
            self._accept_cookies()

            # Preenche email
            print("[SELENIUM] Procurando campo de email...")
            email_field = self.wait.until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            print("[SELENIUM] Campo de email encontrado, limpando...")
            email_field.clear()
            random_wait(0.5, 1.5, "após limpar campo de email")
            print("[SELENIUM] Preenchendo email...")
            # Simula digitação humana
            for char in creds['email']:
                email_field.send_keys(char)
                random_wait(0.1, 0.3)
            random_wait(0.8, 1.5, "após preencher email")
            print("[SELENIUM] Email preenchido com sucesso")

            # Preenche senha
            print("[SELENIUM] Procurando campo de senha...")
            password_field = self.wait.until(
                EC.presence_of_element_located((By.ID, "password"))
            )
            print("[SELENIUM] Campo de senha encontrado, limpando...")
            password_field.clear()
            print("[SELENIUM] Preenchendo senha...")
            # Simula digitação humana da senha
            for char in creds['password']:
                password_field.send_keys(char)
                random_wait(0.1, 0.3)
            print("[SELENIUM] Senha preenchida com sucesso")
            random_wait(1, 2, "após preencher senha")

            # Clica no botão de login
            print("[SELENIUM] Procurando botão de login...")
            login_button = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="login-submit-button"]'))
            )
            print("[SELENIUM] Botão de login encontrado, tentando clicar...")
            
            # Tenta diferentes métodos de clique
            try:
                login_button.click()
                print("[SELENIUM] Clique direto no botão realizado com sucesso")
            except:
                try:
                    print("[SELENIUM] Tentando clique alternativo via ActionChains...")
                    ActionChains(self.driver).move_to_element(login_button).click().perform()
                    print("[SELENIUM] Clique via ActionChains realizado com sucesso")
                except:
                    print("[SELENIUM] Tentando clique via JavaScript...")
                    self.driver.execute_script("arguments[0].click();", login_button)
                    print("[SELENIUM] Clique via JavaScript realizado com sucesso")

            print("[LOGIN] Aguardando redirecionamento...")
            random_wait(5, 8, "aguardando redirecionamento após login")

            # Verifica sucesso do login
            try:
                print("[SELENIUM] Aguardando processamento do login...")
                random_wait(2, 4, "processando login")
                
                print("[SELENIUM] Verificando se formulário de login desapareceu...")
                self.wait.until_not(
                    EC.presence_of_element_located((By.ID, "username"))
                )
                print("[SELENIUM] Formulário de login não está mais visível")
                
                print("[SELENIUM] Verificando URL atual...")
                if "login" not in self.driver.current_url:
                    print("[SELENIUM] URL indica sucesso no login")
                    
                    # Verifica se elementos de usuário logado estão presentes
                    print("[SELENIUM] Procurando elementos de usuário logado...")
                    try:
                        self.wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="myolx-link"]'))
                        )
                        print("[SELENIUM] Elementos de usuário logado encontrados - Login bem sucedido!")
                        return True
                    except:
                        print("[SELENIUM] Elementos de usuário logado não encontrados - Possível falha no login")
                        return False
                else:
                    print("[LOGIN] Falha no login - ainda na página de login")
                    return False
                    
            except Exception as e:
                print(f"[LOGIN] Erro ao verificar status do login: {str(e)}")
                return False

        except Exception as e:
            print(f"[LOGIN] Erro no processo de login: {str(e)}")
            # Tenta rotacionar para outro proxy em caso de falha
            if self.proxies:
                next_proxy = rotate_proxy(self.proxies, self.current_proxy)
                if next_proxy and next_proxy != self.current_proxy:
                    print(f"[PROXY] Rotacionando para próximo proxy: {next_proxy}")
                    self.current_proxy = next_proxy
                    return self._login(force_login)  # Tenta login novamente com novo proxy
            return False
    def extract_data(self, url: str, progress_callback=None) -> ScrapingData:
        print(f"\nIniciando extração de dados da URL: {url}")
        start_time = time.time()
        
        # Verifica status do proxy atual
        if self.current_proxy:
            print(f"[PROXY] Verificando proxy atual: {self.current_proxy}")
            if not test_proxy(self.current_proxy):
                print("[PROXY] Proxy atual não está respondendo, tentando rotacionar...")
                next_proxy = rotate_proxy(self.proxies, self.current_proxy)
                if next_proxy and next_proxy != self.current_proxy:
                    print(f"[PROXY] Rotacionando para: {next_proxy}")
                    self.current_proxy = next_proxy
                    # Atualiza configuração do proxy no Chrome
                    proxy = Proxy()
                    proxy.proxy_type = ProxyType.MANUAL
                    proxy.http_proxy = self.current_proxy
                    proxy.ssl_proxy = self.current_proxy
                    self.driver.proxy = proxy
        try:
            # Tenta fazer login primeiro
            if not self._login():
                raise Exception("Não foi possível realizar o login. Verifique as credenciais.")

            # Validação de proxy antes de navegar
            if self.current_proxy:
                print(f"[PROXY] Validando proxy antes de navegar: {self.current_proxy}")
                proxy_attempts = 0
                max_proxy_attempts = 3
                
                while not test_proxy(self.current_proxy) and proxy_attempts < max_proxy_attempts:
                    print(f"[PROXY] Tentativa {proxy_attempts + 1}: Proxy atual não está respondendo")
                    next_proxy = rotate_proxy(self.proxies, self.current_proxy)
                    if next_proxy and next_proxy != self.current_proxy:
                        print(f"[PROXY] Rotacionando para: {next_proxy}")
                        self.current_proxy = next_proxy
                        # Atualiza configuração do proxy no Chrome
                        proxy = Proxy()
                        proxy.proxy_type = ProxyType.MANUAL
                        proxy.http_proxy = self.current_proxy
                        proxy.ssl_proxy = self.current_proxy
                        self.driver.proxy = proxy
                    proxy_attempts += 1
                    time.sleep(2)  # Pequena pausa entre tentativas
                
                if proxy_attempts >= max_proxy_attempts:
                    print("[PROXY] AVISO: Não foi possível encontrar um proxy válido após múltiplas tentativas")
            
            print(f"[TIMING] Iniciando navegação para URL principal...")
            load_start = time.time()
            self.driver.get(url)
            print(f"[TIMING] URL principal carregada em: {time.time() - load_start:.2f}s")
            print("[STATUS] Verificando elementos da página...")
            
            # Aceita cookies se presente
            self._accept_cookies()
            
            # Lista para armazenar os dados extraídos
            extracted_data = []

            # Espera inicial variável para carregamento da página
            wait_time = random.uniform(4, 7)
            print(f"[SELENIUM] Aguardando {wait_time:.1f}s para carregamento inicial...")
            time.sleep(wait_time)
            
            # Simula comportamento humano de scroll
            for _ in range(3):
                scroll_amount = random.randint(300, 700)
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                time.sleep(random.uniform(1, 2.5))
            
            # Espera os anúncios carregarem com retry
            max_retries = 3
            for retry in range(max_retries):
                try:
                    anuncios = self.wait.until(
                        EC.presence_of_all_elements_located((By.CLASS_NAME, 'css-1apmciz'))
                    )
                    total_anuncios = len(anuncios)
                    if total_anuncios > 0:
                        break
                except TimeoutException:
                    if retry < max_retries - 1:
                        print(f"Tentativa {retry + 1} falhou, tentando novamente...")
                        self.driver.refresh()
                        time.sleep(2)
                    else:
                        raise
            print(f"Encontrados {total_anuncios} anúncios para processar")
            
            # Coleta todos os links primeiro
            links = []
            for div in anuncios:
                try:
                    link_tag = div.find_element(By.CSS_SELECTOR, 'a.css-1tqlkj0')
                    full_link = link_tag.get_attribute('href')
                    links.append(full_link)
                except Exception as e:
                    logging.error(f"Erro ao extrair link: {str(e)}")
                    continue

            # Processa cada link individualmente
            for index, full_link in enumerate(links, 1):
                if progress_callback:
                    progress = (index / len(links)) * 100
                    progress_callback(progress, f"Processando item {index} de {len(links)}")
                
                # Rotação periódica de proxy a cada 5 itens
                if index % 5 == 0 and self.proxies:
                    print("[PROXY] Realizando rotação periódica de proxy...")
                    next_proxy = rotate_proxy(self.proxies, self.current_proxy)
                    if next_proxy and next_proxy != self.current_proxy:
                        print(f"[PROXY] Rotacionando para: {next_proxy}")
                        self.current_proxy = next_proxy
                        # Atualiza configuração do proxy no Chrome
                        proxy = Proxy()
                        proxy.proxy_type = ProxyType.MANUAL
                        proxy.http_proxy = self.current_proxy
                        proxy.ssl_proxy = self.current_proxy
                        self.driver.proxy = proxy

                try:
                    item_start_time = time.time()
                    print(f"\n[TIMING] Iniciando processamento do item {index}")

                    # Limpa o cache a cada 3 itens
                    if index % 3 == 0:
                        self.driver.execute_script("""
                            window.performance.clearResourceTimings();
                            window.performance.clearMeasures();
                            window.performance.clearMarks();
                            window.localStorage.clear();
                            window.sessionStorage.clear();
                        """)
                        
                    # Tenta carregar a página com comportamento mais natural
                    print(f"[SELENIUM] Navegando para anúncio {index}...")
                    self.driver.get(full_link)
                    
                    # Espera variável após carregar nova página
                    wait_time = random.uniform(5, 8)
                    print(f"[SELENIUM] Aguardando {wait_time:.1f}s para carregamento...")
                    time.sleep(wait_time)
                    
                    # Simula scroll suave na página
                    for _ in range(2):
                        scroll_amount = random.randint(200, 500)
                        self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                        time.sleep(random.uniform(0.8, 1.5))
                    
                    # Verifica se página carregou
                    self.wait.until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    print(f"[TIMING] Link do item carregado: {time.time() - item_start_time:.2f}s")

                    # Extrai dados do anúncio
                    title = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="ad_title"] h4'))
                    ).text.strip()

                    price = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="ad-price-container"] h3'))
                    ).text.strip()

                    seller_name = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '.css-1fp4ipz h4.css-fka1fu'))
                    ).text.strip()

                    # Tenta obter o telefone
                    phone_number = "Número não disponível"
                    try:
                        phone_button = self.wait.until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="ad-contact-phone"]'))
                        )
                        # Simula movimento do mouse antes de clicar
                        actions = ActionChains(self.driver)
                        actions.move_to_element(phone_button)
                        actions.pause(random.uniform(0.3, 0.7))
                        actions.click()
                        actions.perform()
                        
                        # Espera variável após clicar
                        wait_time = random.uniform(3, 5)
                        print(f"[SELENIUM] Aguardando {wait_time:.1f}s após clicar no botão do telefone...")
                        time.sleep(wait_time)

                        phone_link = self.wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[data-testid="contact-phone"][href^="tel:"]'))
                        )
                        phone_number = phone_link.text.strip()
                    except Exception as phone_error:
                        print(f"Erro ao obter telefone: {str(phone_error)}")

                    # Adiciona os dados extraídos
                    extracted_data.append({
                        'title': title,
                        'price': price,
                        'seller': seller_name,
                        'phone': phone_number,
                        'link': full_link
                    })
                    print(f"Extraído: {title} - {price} - Vendedor: {seller_name} - Telefone: {phone_number}")

                except Exception as e:
                    print(f"Erro ao processar item {index}: {str(e)}")
                    # Tenta rotacionar proxy em caso de erro
                    if self.proxies:
                        next_proxy = rotate_proxy(self.proxies, self.current_proxy)
                        if next_proxy and next_proxy != self.current_proxy:
                            print(f"[PROXY] Rotacionando para próximo proxy: {next_proxy}")
                            self.current_proxy = next_proxy
                            # Reconfigura proxy para o Chrome
                            options = self.driver.options
                            proxy = Proxy()
                            proxy.proxy_type = ProxyType.MANUAL
                            proxy.http_proxy = self.current_proxy
                            proxy.ssl_proxy = self.current_proxy
                            options.proxy = proxy
                            
                            # Reinicia o navegador com o novo proxy
                            self.driver.quit()
                            self.driver = webdriver.Chrome(options=options)
                            self.driver.set_page_load_timeout(self.current_wait_time * 2)
                            self.driver.set_script_timeout(self.current_wait_time)
                            self.wait = WebDriverWait(self.driver, self.current_wait_time)
                            self.short_wait = WebDriverWait(self.driver, max(self.min_wait_time, self.current_wait_time // 2))
                            
                            # Tenta processar o item novamente
                            try:
                                self.driver.get(full_link)
                                continue
                            except:
                                pass
                    continue

            return ScrapingData(url=url, data=extracted_data)

        except Exception as e:
            raise Exception(f"Erro ao extrair dados: {str(e)}")
        finally:
            print("\nFinalizando extração...")
            self.driver.quit()

    def transform_data(self, data: ScrapingData) -> dict:
        """Transforma os dados extraídos no formato desejado"""
        return data.data


    def __del__(self):
        try:
            self.driver.quit()
        except:
            pass