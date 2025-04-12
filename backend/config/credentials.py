import os
import json
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

class CredentialsManager:
    def __init__(self):
        self.config_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        self.key_file = self.config_dir / 'secret.key'
        self.cred_file = self.config_dir / 'credentials.enc'
        self._ensure_key()

    def _ensure_key(self):
        """Garante que a chave de criptografia existe"""
        if not self.key_file.exists():
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)

    def _get_fernet(self):
        """Retorna instância Fernet para criptografia"""
        with open(self.key_file, 'rb') as f:
            key = f.read()
        return Fernet(key)

    def save_credentials(self, email: str, password: str):
        """Salva credenciais tanto no .env quanto no arquivo criptografado"""
        # Atualiza o arquivo .env
        env_path = Path('.env')
        print(f"[DEBUG] Tentando salvar credenciais em: {env_path.absolute()}")
        print(f"[DEBUG] Arquivo .env existe? {env_path.exists()}")
        env_content = []
        
        if env_path.exists():
            with open(env_path, 'r') as f:
                env_content = f.readlines()
        
        # Remove linhas antigas de credenciais se existirem
        env_content = [line for line in env_content if not line.startswith(('OLX_EMAIL=', 'OLX_PASSWORD='))]
        
        # Adiciona novas credenciais
        env_content.extend([
            f"OLX_EMAIL={email}\n",
            f"OLX_PASSWORD={password}\n"
        ])
        
        # Salva o arquivo .env atualizado
        try:
            with open(env_path, 'w') as f:
                f.writelines(env_content)
            print(f"[DEBUG] Permissões do arquivo .env: {oct(env_path.stat().st_mode)[-3:]}")
        except Exception as e:
            print(f"[DEBUG] Erro ao escrever .env: {str(e)}")
            raise
            
        print("[CRED] Credenciais atualizadas no arquivo .env")
        
        # Força recarregamento das variáveis de ambiente
        os.environ.clear()  # Limpa as variáveis atuais
        load_dotenv(override=True)  # Recarrega forçando override
        
        # Verifica se as credenciais foram recarregadas corretamente
        loaded_email = os.getenv('OLX_EMAIL')
        loaded_password = os.getenv('OLX_PASSWORD')
        print(f"[DEBUG] Verificação pós-salvamento - Email carregado: {bool(loaded_email)}, Senha carregada: {bool(loaded_password)}")
        
        # Salva também no arquivo criptografado como backup
        f = self._get_fernet()
        creds = {
            'email': email,
            'password': password
        }
        encrypted_data = f.encrypt(json.dumps(creds).encode())
        with open(self.cred_file, 'wb') as file:
            file.write(encrypted_data)
            
        print("[CRED] Credenciais salvas no arquivo criptografado")

    def get_credentials(self):
        """Recupera credenciais salvas, primeiro do .env depois do arquivo criptografado"""
        # Tenta primeiro do .env
        print("[DEBUG] Carregando variáveis de ambiente...")
        load_dotenv()  # Recarrega as variáveis para garantir
        env_email = os.getenv('OLX_EMAIL')
        env_password = os.getenv('OLX_PASSWORD')
        print(f"[DEBUG] Credenciais encontradas no .env? Email: {bool(env_email)}, Senha: {bool(env_password)}")
        
        if env_email and env_password:
            print("[CRED] Usando credenciais do arquivo .env")
            return {
                'email': env_email,
                'password': env_password
            }
            
        # Se não encontrar no .env, tenta do arquivo criptografado
        if not self.cred_file.exists():
            print("[DEBUG] Arquivo de credenciais criptografado não encontrado")
            return None
        
        print("[CRED] Usando credenciais do arquivo criptografado")
        f = self._get_fernet()
        try:
            with open(self.cred_file, 'rb') as file:
                encrypted_data = file.read()
            decrypted_data = f.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            print(f"Erro ao recuperar credenciais: {str(e)}")
            return None