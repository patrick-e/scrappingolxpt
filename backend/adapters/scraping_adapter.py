import random
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

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

def _manage_proxy_cache(proxy: str = None, valid: bool = True) -> None:
    """Gerencia o cache de proxies."""
    if not hasattr(BeautifulSoupAdapter, '_proxy_cache'):
        BeautifulSoupAdapter._proxy_cache = set()
    if proxy:
        if valid:
            BeautifulSoupAdapter._proxy_cache.add(proxy)
        else:
            BeautifulSoupAdapter._proxy_cache.discard(proxy)

def _get_cached_proxies() -> list[str]:
    """Retorna proxies do cache."""
    if not hasattr(BeautifulSoupAdapter, '_proxy_cache'):
        BeautifulSoupAdapter._proxy_cache = set()
    return list(BeautifulSoupAdapter._proxy_cache)

def fetch_random_proxies() -> list[str]:
    """Busca e testa proxies de múltiplas fontes de forma paralela."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Verifica cache primeiro
    cached_proxies = _get_cached_proxies()
    if cached_proxies:
        valid_cached = [p for p in cached_proxies if test_proxy(p, timeout=2)]
        if len(valid_cached) >= 5:
            print(f"[PROXY] Usando {len(valid_cached)} proxies do cache")
            return valid_cached[:10]

    # Lista de APIs de proxy (reduzida para maior confiabilidade)
    proxy_apis = [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=1000&country=all&ssl=all&anonymity=all"
    ]
    
    def fetch_from_api(api):
        try:
            pass  # Add the intended logic here
        except Exception as e:
            print(f"[ERROR] An error occurred: {e}")
            response = requests.get(api, timeout=5)
            if response.status_code == 200:
                return set(response.text.splitlines())
        except Exception as e:
            print(f"[PROXY] Erro ao buscar proxies de {api}: {str(e)}")
        return set()

    def test_proxies_batch(proxies):
        working = []
        for proxy in proxies:
            if test_proxy(proxy, timeout=2):  # Reduzido timeout para 2 segundos
                working.append(proxy)
                if len(working) >= 1:  # Reduzido para 1 proxy por batch
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
            if len(working_proxies) >= 5:  # Reduzido número máximo de proxies
                break

    # Atualiza o cache com os novos proxies válidos
    for proxy in working_proxies:
        _manage_proxy_cache(proxy, valid=True)
    
    random.shuffle(working_proxies)
    return working_proxies[:10]

def test_proxy(proxy: str, timeout: int = 3) -> bool:
    """Testa se um proxy está funcionando e pode acessar a OLX corretamente."""
    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
    try:
        # Primeiro teste rápido com Google
        response = requests.get("https://www.google.com", proxies=proxies, timeout=timeout)
        if response.status_code != 200:
            print(f"[PROXY] {proxy} falhou no teste do Google")
            return False
            
        # Teste detalhado com OLX
        response = requests.get("https://www.olx.pt", proxies=proxies, timeout=timeout)
        if response.status_code != 200:
            print(f"[PROXY] {proxy} falhou no acesso à OLX")
            return False
            
        # Verificações de conteúdo da OLX
        content = response.text.lower()
        indicators = [
            'olx.pt',
            'data-testid',  # Indicador de elementos da interface
            'myolx-link',   # Indicador do botão de login
            'css-'          # Indicador de classes CSS da OLX
        ]
        
        for indicator in indicators:
            if indicator not in content:
                print(f"[PROXY] {proxy} falhou na verificação de conteúdo: {indicator}")
                return False
                
        print(f"[PROXY] {proxy} passou em todas as verificações")
        return True
    except Exception:
        return False

def rotate_proxy(proxies: list[str], current_proxy: str, proxy_fail_count: dict = None) -> str:
    """Seleciona um novo proxy diferente do atual, considerando histórico de falhas."""
    if not proxies:
        return None
        
    # Filtra proxies com muitas falhas
    if proxy_fail_count:
        available_proxies = [p for p in proxies if p != current_proxy and proxy_fail_count.get(p, 0) < 3]
    else:
        available_proxies = [p for p in proxies if p != current_proxy]
        
    if not available_proxies and proxies:
        # Reseta contadores de falha se todos os proxies falharam
        if proxy_fail_count:
            proxy_fail_count.clear()
        return random.choice(proxies)
        
    return random.choice(available_proxies) if available_proxies else None

def _handle_proxy_failure(self, proxy: str) -> None:
    """Gerencia falhas de proxy e atualiza contadores."""
    if proxy:
        self._proxy_fail_count[proxy] = self._proxy_fail_count.get(proxy, 0) + 1
        if self._proxy_fail_count[proxy] >= self._max_proxy_fails:
            if proxy in self.proxies:
                self.proxies.remove(proxy)
            if proxy in self._proxy_cache:
                self._proxy_cache.remove(proxy)

class BeautifulSoupAdapter(ScrapingServicePort):
    """Adaptador para extração de dados da OLX usando Selenium e BeautifulSoup.
    
    Responsável por:
    - Gerenciar sessão do navegador e autenticação
    - Extrair lista de anúncios das páginas de busca
    - Processar detalhes de cada anúncio individual
    - Extrair informações de contato dos vendedores
    
    Attributes:
        email (str): Email para login
        password (str): Senha para login
        driver (webdriver.Chrome): Instância do navegador
        proxies (list): Lista de proxies disponíveis
        current_proxy (str): Proxy atual em uso
        retry_count (int): Número de tentativas para operações
        min_request_delay (float): Delay mínimo entre requisições
    """
    
    def __init__(self, email=None, password=None, proxies=None):
        self.proxies = proxies or []
        self.current_proxy = None
        self.driver = None
        self.email = email
        self.password = password
        self.retry_count = 3
        self.last_request = 0
        self.min_request_delay = 1.0
        self.user_agent = UserAgent()
        self._proxy_cache = set()
        self._proxy_fail_count = {}
        self._max_proxy_fails = 3
        self._proxy_timeout = 5
        
    def _respect_rate_limit(self):
        """Controla intervalo entre requisições."""
        now = time.time()
        delay = self.min_request_delay - (now - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.time()
        
    def _get_chrome_options(self) -> webdriver.ChromeOptions:
        """Configura opções do Chrome para scraping com rotação de user-agent e proteções anti-detecção."""
        options = webdriver.ChromeOptions()
        
        # User-Agent aleatório
        random_user_agent = self.user_agent.random
        options.add_argument(f'--user-agent={random_user_agent}')
        
        # Performance e Privacidade
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        
        # Anti-detecção avançada
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-blink-features')
        options.add_argument('--disable-infobars')
        options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Privacidade e cache aprimorados
        prefs = {
            'profile.default_content_settings.popups': 0,
            'credentials_enable_service': False,
            'profile.password_manager_enabled': False,
            'profile.managed_default_content_settings.images': 1,
            'profile.managed_default_content_settings.javascript': 1,
            'profile.default_content_setting_values.notifications': 2,
            'profile.managed_default_content_settings.plugins': 1,
            'profile.default_content_settings.geolocation': 2,
            'profile.default_content_settings.media_stream': 2
        }
        options.add_experimental_option('prefs', prefs)
        
        # Configurações adicionais de navegador
        options.add_argument('--disable-web-security')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--allow-running-insecure-content')
        
    def _initialize_browser(self):
        """Inicializa navegador com configurações otimizadas."""
        try:
            if self.driver:
                self._cleanup_driver()

            options = self._get_chrome_options()
            
            if self.current_proxy:
                options.add_argument(f'--proxy-server={self.current_proxy}')
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(3)
            self.driver.set_window_size(1920, 1080)
            
            print("[BROWSER] Navegador inicializado")
            return True
            
        except Exception as e:
            print(f"[BROWSER] Erro: {e}")
            self._cleanup_driver()
            return False
    
    
    def _accept_cookies(self, wait: WebDriverWait) -> bool:
        """Aceita cookies se necessário."""
        for selector in ['#onetrust-accept-btn-handler',
                        'button[data-testid="cookie-policy-dialog-accept-button"]']:
            try:
                btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                btn.click()
                time.sleep(0.3)
                return True
            except:
                continue
        return False
        
    def login(self, progress_callback=None) -> bool:
        """Realiza login no site usando credenciais configuradas."""
        try:
            if not self.email or not self.password:
                raise ValueError("Credenciais não configuradas")
            
            # Inicializar browser
            if progress_callback:
                progress_callback(10, "Iniciando navegador...")
            if not self._initialize_browser():
                raise Exception("Falha ao inicializar navegador")
            
            # Acessar site
            self.driver.get("https://www.olx.pt")
            wait = WebDriverWait(self.driver, 3)
            
            if progress_callback:
                progress_callback(30, "Aceitando cookies...")
            self._accept_cookies(wait)
            time.sleep(0.3)
            
            # Clicar no botão de login
            if progress_callback:
                progress_callback(50, "Acessando login...")
            try:
                btn = wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'a[data-cy="myolx-link"]')
                ))
                btn.click()
                time.sleep(0.3)
            except:
                raise Exception("Botão de login não encontrado")
            
            # Preencher formulário
            if progress_callback:
                progress_callback(70, "Preenchendo credenciais...")
            try:
                # Email
                email_field = wait.until(EC.presence_of_element_located((By.ID, 'username')))
                email_field.clear()
                email_field.send_keys(self.email)
                time.sleep(0.2)
                
                # Senha
                pass_field = wait.until(EC.presence_of_element_located((By.ID, 'password')))
                pass_field.clear()
                pass_field.send_keys(self.password)
                time.sleep(0.2)
                
                # Submit
                pass_field.send_keys(Keys.RETURN)
                time.sleep(0.3)
                
                if progress_callback:
                    progress_callback(100, "Login realizado!")
                return True
                
            except Exception as e:
                raise Exception(f"Erro ao preencher formulário: {e}")
            
        except Exception as e:
            print(f"[LOGIN] Erro: {e}")
            self._cleanup_driver()
            return False


    def _process_items(self, items: list, progress_callback=None) -> list:
        """Processa cada item para extrair detalhes adicionais."""
        processed = []
        total = len(items)
        
        for idx, item in enumerate(items, 1):
            try:
                if progress_callback:
                    progress_callback(40 + (idx/total * 60),
                                   f"Item {idx}/{total}")

                self._respect_rate_limit()
                self.driver.get(item['link'])
                
                wait = WebDriverWait(self.driver, 5)
                self._accept_cookies(wait)
                time.sleep(0.3)

                # Extrair telefone
                phone = self._extract_phone(wait)
                item['phone'] = phone if phone else 'N/A'
                processed.append(item)

            except Exception as e:
                print(f"[PROCESS] Erro no item {idx}: {e}")
                item['phone'] = 'N/A'
                processed.append(item)

        return processed


            
    def scrape(self, url: str, progress_callback=None) -> ScrapingData:
        """
        Método principal de scraping, implementando a interface ScrapingServicePort.
        
        Args:
            url (str): URL da página de busca da OLX
            progress_callback (callable): Função para reportar progresso
            
        Returns:
            ScrapingData: Dados extraídos formatados
            
        Raises:
            Exception: Erros durante o processo de scraping
        """
        return self.extract_data(url, progress_callback)


    def __del__(self):
        """Destrutor para garantir limpeza de recursos."""
        self._cleanup_driver()

    def extract_data(self, url: str, progress_callback=None) -> ScrapingData:
        """Extrai dados dos anúncios da URL fornecida com rotação automática de IP e proxy."""
        try:
            self._init_proxies(progress_callback)
            
            # Primeiro extrai a lista de itens usando BeautifulSoup (sem login)
            items_data = []
            for attempt in range(self.retry_count):
                try:
                    items_data = self._extract_items_list(url, progress_callback)
                    if items_data:
                        break
                except Exception as e:
                    print(f"[EXTRACT] Erro na listagem {attempt + 1}: {str(e)}")
                    self._handle_proxy_failure(self.current_proxy)
                    self.current_proxy = rotate_proxy(self.proxies, self.current_proxy, self._proxy_fail_count)
                    
                    # Se não houver proxies disponíveis ou muitas falhas, busca novos
                    if not self.current_proxy or attempt % 2 == 1:
                        print("[PROXY] Buscando novos proxies...")
                        self.proxies = fetch_random_proxies()
                        self.current_proxy = rotate_proxy(self.proxies, None)
                    
                    time.sleep(min(1.5 * (attempt + 1), 4))
            
            if not items_data:
                raise Exception("Não foi possível extrair a lista de itens após todas as tentativas")
            
            # Processa os detalhes usando Selenium com rotação de IP/proxy
            retry_count = self.retry_count * 2  # Aumenta tentativas para detalhes
            for attempt in range(retry_count):
                try:
                    # Alterna user-agent a cada tentativa
                    if self.driver:
                        self._cleanup_driver()
                        self.driver = None
                        
                    detailed_data = self._process_items(items_data, progress_callback)
                    return ScrapingData(url, detailed_data)
                    
                except Exception as e:
                    print(f"[EXTRACT] Erro no processamento {attempt + 1}: {str(e)}")
                    self._handle_proxy_failure(self.current_proxy)
                    
                    # Rotaciona proxy e tenta novamente
                    self.current_proxy = rotate_proxy(self.proxies, self.current_proxy, self._proxy_fail_count)
                    if not self.current_proxy or attempt % 3 == 0:
                        print("[PROXY] Buscando novos proxies...")
                        self.proxies = fetch_random_proxies()
                        self.current_proxy = rotate_proxy(self.proxies, None)
                    
                    time.sleep(min(2 * (attempt + 1), 8))
                    
            raise Exception("Falha na extração de dados após todas as tentativas")
                    
        except Exception as e:
            print(f"[EXTRACT] Erro crítico: {str(e)}")
            self._cleanup_driver()
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

        self.driver.set_page_load_timeout(8)  # Mantido acima de 5s por ser carregamento de página
        self.driver.get(url)

        if progress_callback:
            progress_callback(50, "Extraindo dados da página...")

        wait = WebDriverWait(self.driver, 4)  # Reduzido para 4 segundos
        data = self._extract_elements(url, wait)
        
        if progress_callback:
            progress_callback(100, "Extração concluída com sucesso!")
            
        return data

    def _check_login(self) -> bool:
        """Verifica se ainda está logado e se o IP não está bloqueado."""
        try:
            # Verifica login
            is_logged = bool(self.driver.find_element(By.CSS_SELECTOR, '[data-testid="myaccount-link-logged"]'))
            if not is_logged:
                return False
                
            # Verifica se página está acessível
            if self._is_ip_blocked():
                print("[LOGIN] IP atual bloqueado, tentando recuperar...")
                self._handle_ip_block()
                return False
                
            return True
            
        except NoSuchElementException:
            return False
        except Exception as e:
            print(f"[LOGIN] Erro ao verificar login: {e}")
            return False

    def _is_ip_blocked(self) -> bool:
        """Verifica se o IP atual está bloqueado."""
        blocked_indicators = [
            '//div[contains(text(), "blocked")]',
            '//div[contains(text(), "security check")]',
            '//div[contains(text(), "captcha")]',
            '//div[contains(text(), "verificação")]'
        ]
        
        try:
            for indicator in blocked_indicators:
                if self.driver.find_elements(By.XPATH, indicator):
                    return True
            return False
        except Exception as e:
            print(f"[IP_CHECK] Erro ao verificar bloqueio: {e}")
            return True  # Assume bloqueado em caso de erro
            
    def _handle_ip_block(self) -> bool:
        """Tenta recuperar de um bloqueio de IP."""
        try:
            # Limpa cookies e cache
            self.driver.delete_all_cookies()
            
            # Rotaciona proxy e user agent
            old_proxy = self.current_proxy
            self.current_proxy = rotate_proxy(self.proxies, self.current_proxy, self._proxy_fail_count)
            
            # Se não conseguiu novo proxy, busca mais
            if not self.current_proxy or self.current_proxy == old_proxy:
                self.proxies = fetch_random_proxies()
                self.current_proxy = rotate_proxy(self.proxies, old_proxy)
            
            # Reinicializa navegador com novas configurações
            if self.driver:
                self._cleanup_driver()
                self.driver = None
            
            return bool(self.current_proxy)
        except Exception as e:
            print(f"[IP_BLOCK] Erro ao tentar recuperar: {e}")
            return False

    def _extract_items_list(self, url: str, progress_callback=None) -> list:
        """Extrai lista de itens da página usando BeautifulSoup com suporte a paginação e rotação de IP."""
        all_items = []
        current_page = 1
        has_next = True
        session = requests.Session()
        
        # Configura a sessão com user-agent aleatório
        session.headers.update({'User-Agent': self.user_agent.random})
        
        while has_next and current_page <= 20:  # Reduzido para 20 páginas
            self._respect_rate_limit()
            page_url = f"{url}?page={current_page}" if current_page > 1 else url
            
            try:
                # Configura proxy se disponível
                proxies = None
                if self.current_proxy:
                    proxies = {
                        "http": f"http://{self.current_proxy}",
                        "https": f"http://{self.current_proxy}"
                    }
                
                # Tenta fazer a requisição com retry em caso de erro
                for attempt in range(3):
                    try:
                        response = session.get(page_url, proxies=proxies, timeout=10)
                        if response.status_code == 200:
                            break
                    except Exception as e:
                        print(f"[EXTRACT] Erro na página {current_page}, tentativa {attempt + 1}: {str(e)}")
                        if attempt < 2:
                            self._handle_proxy_failure(self.current_proxy)
                            self.current_proxy = rotate_proxy(self.proxies, self.current_proxy, self._proxy_fail_count)
                            if self.current_proxy:
                                proxies = {
                                    "http": f"http://{self.current_proxy}",
                                    "https": f"http://{self.current_proxy}"
                                }
                            session.headers.update({'User-Agent': self.user_agent.random})
                            time.sleep(2)
                        else:
                            raise
            
            if progress_callback:
                progress_callback(30, f"Extraindo itens da página {current_page}...")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            items = []
            
            # Seletores possíveis para diferentes estruturas de página
            selectors = {
                'container': [
                    'div[data-cy="l-card"]',  # Seletor principal de cartão
                    'div.css-1sw7q4x',  # Novo layout
                    'div[data-testid="ad-card"]'  # Fallback
                ],
                'link': [
                    'a[data-cy="listing-link"]',  # Link principal
                    'a[href*="/anuncio/"]',  # Link de anúncio
                    'a[href*="/d/"]',  # Link direto
                ],
                'name': [
                    'h6[data-testid="ad-title"]',  # Título principal
                    'h2.css-1pvw9s4',  # Título novo layout
                    'div[data-testid="ad-title"] h6'  # Título em container
                ],
                'price': [
                    'span[data-testid="ad-price"]',  # Preço principal
                    'p.css-10b0gli',  # Preço novo layout
                    'span[data-testid="price-value"]'  # Preço alternativo
                ],
                'seller': [
                    'span[data-testid="seller-name"]',  # Nome principal
                    'div[data-testid="seller-info"] span',  # Info vendedor
                    'div.css-1f4s4lo'  # Container vendedor
                ]
            }
            
            # Tentar cada seletor até encontrar itens
            item_elements = []
            for container in selectors['container']:
                items = soup.select(container)
                if items:
                    item_elements = items
                    print(f"[EXTRACT] Encontrados {len(items)} itens usando seletor {container}")
                    break

            if not item_elements:
                print("[EXTRACT] Nenhum item encontrado nesta página")
                break

            for item_elem in item_elements:
                item_data = {'name': 'N/A', 'price': 'N/A', 'seller_name': 'N/A', 'link': None}
                
                try:
                    # 1. Extrair e validar link
                    for selector in selectors['link']:
                        try:
                            link_elem = item_elem.select_one(selector)
                            if link_elem and link_elem.has_attr('href'):
                                link = link_elem['href']
                                if not link.startswith('http'):
                                    link = f"https://www.olx.pt{link}"
                                if 'olx.pt' in link:
                                    item_data['link'] = link
                                    print(f"[EXTRACT] Link encontrado: {link}")
                                    break
                        except Exception as e:
                            print(f"[EXTRACT] Erro ao extrair link com seletor {selector}: {e}")
                            continue
                    
                    if not item_data['link']:
                        print("[EXTRACT] Link inválido, pulando item")
                        continue
                    
                    # 2. Extrair outros dados
                    for field in ['name', 'price', 'seller_name']:
                        for selector in selectors[field]:
                            try:
                                elem = item_elem.select_one(selector)
                                if elem:
                                    text = elem.get_text(strip=True)
                                    if text:
                                        item_data[field] = text
                                        print(f"[EXTRACT] {field}: {text}")
                                        break
                            except Exception as e:
                                print(f"[EXTRACT] Erro ao extrair {field}: {e}")
                                continue
                    
                    # 3. Validar e adicionar item
                    required_fields = ['name', 'link']
                    optional_fields = ['price', 'seller_name']
                    
                    # Verificar campos obrigatórios
                    if all(item_data[field] != 'N/A' and item_data[field] is not None for field in required_fields):
                        # Garantir que pelo menos um campo opcional tem valor
                        if any(item_data[field] != 'N/A' for field in optional_fields):
                            items.append(item_data)
                            print(f"[EXTRACT] Item adicionado: {item_data['name'][:30]}...")
                        else:
                            print("[EXTRACT] Item sem dados opcionais, ignorando")
                    else:
                        print("[EXTRACT] Item sem dados obrigatórios, ignorando")
                    
                except Exception as e:
                    print(f"[EXTRACT] Erro ao extrair item: {str(e)}")
                    continue

            print(f"[EXTRACT] {len(items)} itens processados nesta página")
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

    def _extract_phone(self, wait: WebDriverWait) -> str | None:
        """Extrai o número de telefone da página atual."""
        try:
            # Tentar botões que revelam o telefone
            for btn_selector in [
                "//button[contains(@data-testid, 'reveal-phone')]",
                "//button[contains(@data-cy, 'show-phone')]",
                "//button[contains(text(), 'telefone')]"
            ]:
                try:
                    btn = wait.until(EC.element_to_be_clickable((By.XPATH, btn_selector)))
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(0.5)
                        break
                except:
                    continue

            # Buscar número revelado
            for phone_selector in [
                "//span[contains(@data-testid, 'contact-phone')]",
                "//div[contains(@data-testid, 'phone-number')]//span",
                "//a[starts-with(@href, 'tel:')]"
            ]:
                try:
                    element = wait.until(EC.presence_of_element_located((By.XPATH, phone_selector)))
                    if element.is_displayed():
                        phone = element.text or element.get_attribute('href')
                        if phone:
                            phone = ''.join(c for c in phone if c.isdigit() or c == '+')
                            if phone and len(phone) > 8:
                                print(f"[PHONE] Encontrado: {phone}")
                                return phone
                except:
                    continue

            return None
            
        except Exception as e:
            print(f"[PHONE] Erro: {e}")
            return None

    def _process_items(self, items: list, progress_callback=None) -> list:
        """Processa lista de anúncios para extrair telefones."""
        if not self.driver or not self._check_login():
            credentials = CredentialsManager().get_credentials()
            if not credentials:
                raise Exception("Credenciais não encontradas")
            self.email = credentials['email']
            self.password = credentials['password']
            if not self.login(progress_callback):
                raise Exception("Falha no login")

        processed_items = []
        total = len(items)

        for idx, item in enumerate(items, 1):
            if progress_callback:
                progress = int(40 + (60 * idx / total))
                progress_callback(progress, f"Item {idx}/{total}")

            try:
                self._respect_rate_limit()
                self.driver.get(item['link'])
                wait = WebDriverWait(self.driver, 5)
                
                self._accept_cookies(wait)
                time.sleep(0.3)

                phone = self._extract_phone(wait)
                item['phone'] = phone if phone else 'N/A'
                processed_items.append(item)

            except Exception as e:
                print(f"[ERROR] Item {idx}: {e}")
                item['phone'] = 'N/A'
                processed_items.append(item)

        return processed_items

    def _get_element_text(self, wait: WebDriverWait, xpath: str) -> str:
        """Extrai texto de um elemento com tratamento de timeout."""
        try:
            element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            return element.text.strip()
        except TimeoutException:
            return "N/A"

    def _handle_extraction_error(self, error: Exception, attempt: int, progress_callback=None) -> bool:
        """Processa erros de extração e decide se deve tentar novamente."""
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

