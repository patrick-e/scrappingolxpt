# Web Scraping Tool

Ferramenta de web scraping para OLX.

## Configuração de Credenciais

Existem duas formas de configurar suas credenciais:

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

## Segurança

- O arquivo `.env` deve ser mantido privado e nunca commitado no repositório
- Uma cópia criptografada das credenciais é mantida como backup