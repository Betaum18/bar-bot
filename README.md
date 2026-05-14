# Bar Bot — GTA RP

Bot Discord para gerenciamento de bar em GTA RP: controle de estoque de combos, registro de vendas com foto do baú e rastreamento de dracmas depositados.

## Regra de negócio

- Cada combo vendido = **10 dracmas** depositados no baú
- Toda venda exige **foto do baú** como comprovante

## Instalação

### Pré-requisitos

- Python 3.11+
- pip

### 1. Instalar dependências

```bash
cd bar-bot
pip install -r requirements.txt
```

### 2. Rodar localmente (teste)

```bash
python3 bot.py
```

---

## Rodar em produção com pm2 (Oracle Linux — OCI Free Tier)

### Instalar Node.js e pm2

```bash
# Oracle Linux 8/9
sudo dnf install -y nodejs
sudo npm install -g pm2
```

### Iniciar o bot com pm2

```bash
cd /home/opc/bar-bot
pm2 start bot.py --interpreter python3 --name bar-bot
```

> Se o servidor usar Python 3.11 especificamente:
> ```bash
> pm2 start bot.py --interpreter python3.11 --name bar-bot
> ```

### Salvar e habilitar inicialização automática

```bash
pm2 save
pm2 startup
# Execute o comando que o pm2 mostrar na tela (começa com sudo env ...)
```

### Comandos úteis pm2

```bash
pm2 logs bar-bot        # ver logs em tempo real
pm2 status              # ver status do processo
pm2 restart bar-bot     # reiniciar o bot
pm2 stop bar-bot        # parar o bot
pm2 delete bar-bot      # remover do pm2
```

---

## Estrutura de arquivos

```
bar-bot/
├── bot.py          # código principal
├── data.json       # dados persistidos (estoque, vendas, histórico)
├── panel_id.json   # ID da mensagem do painel (gerado automaticamente)
├── requirements.txt
└── README.md
```

## Funcionalidades

| Botão | Ação |
|---|---|
| 📦 Adicionar Estoque | Modal para registrar combos adicionados |
| 💰 Registrar Venda | Modal com quantidade → pede foto do baú → posta registro |
| 📊 Ver Resumo | Embed com estoque atual, total vendido e dracmas depositados |
