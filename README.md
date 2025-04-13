# Web Scraping Tool para OLX

Ferramenta de web scraping especializada para o site da OLX Portugal, que permite extrair dados de anúncios e informações de contato de vendedores.

## Funcionalidades

- ✅ Extração de dados de anúncios da OLX (títulos, preços, descrições)
- ✅ Captura de números de telefone de contato dos vendedores
- ✅ Paginação automática para buscar resultados em múltiplas páginas
- ✅ Suporte a proxies rotativos para evitar bloqueios
- ✅ Salvamento de dados em formato JSON
- ✅ Exportação para Excel
- ✅ Interface gráfica intuitiva

## Requisitos

- Python 3.10 ou superior
- Dependências listadas em `requirements.txt`
- Navegador Chrome instalado (para o Selenium)

## Instalação

1. Clone o repositório:
   ```
   git clone <repo-url>
   cd webscrapping
   ```

2. Crie e ative um ambiente virtual:
   ```
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # ou
   .venv\Scripts\activate  # Windows
   ```

3. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

## Configuração de Credenciais

Existem duas formas de configurar suas credenciais para acesso à OLX:

1. **Usando arquivo .env (Recomendado)**:
   - Copie o arquivo `.env.example` para `.env`
   - Edite o arquivo `.env` e adicione suas credenciais:
     ```
     OLX_EMAIL=seu_email@exemplo.com
     OLX_PASSWORD=sua_senha
     ```

2. **Via Interface Gráfica**:
   - Se nenhuma credencial for encontrada no `.env`, o programa solicitará login através da interface gráfica
   - As credenciais serão salvas automaticamente tanto no `.env` quanto em um arquivo criptografado

## Uso

Execute o programa principal:

```
python main.py
```

Na interface gráfica:
1. Insira a URL da página de resultados da OLX que deseja extrair
2. Clique em "Iniciar Scraping"
3. Faça login quando solicitado (se necessário)
4. Aguarde a extração dos dados
5. Os dados serão salvos automaticamente em `data.json`

Para exportar os dados para Excel:
1. Após a extração, use o menu para exportar os dados
2. Escolha o local e nome do arquivo Excel

## Arquitetura do Projeto

O projeto segue uma arquitetura limpa (Clean Architecture):

- **Frontend**: Interface gráfica construída com Tkinter
- **Backend**:
  - **Domain**: Contém as entidades e interfaces (ports)
  - **Adapters**: Implementações concretas (BeautifulSoup, Selenium, JSON)
  - **Config**: Gerenciamento de configurações e credenciais

## Segurança

- O arquivo `.env` deve ser mantido privado e nunca commitado no repositório
- Uma cópia criptografada das credenciais é mantida como backup em `backend/config/credentials.enc`
- A chave de criptografia está em `backend/config/secret.key` e deve ser protegida

## Contribuição

Contribuições são bem-vindas! Por favor, sinta-se à vontade para enviar pull requests ou abrir issues para melhorias.

## Notas Importantes

- Este projeto é apenas para fins educacionais
- Use responsavelmente e respeite os termos de serviço da OLX
- Considere limitar a taxa de requisições para evitar sobrecarregar os servidores da OLX