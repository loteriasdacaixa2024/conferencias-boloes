# 🎰 Extrator e Analisador de Bolões da Caixa

Esta pasta contém as ferramentas automatizadas para extrair os bolões de lotéricas diretamente do site oficial das Loterias Caixa. 

## 🎯 Qual é o Objetivo Principal?
O grande objetivo de extrair e analisar esses bolões é **maximizar a sua cobertura matemática gastando o mínimo possível**, garantindo que você não jogue dinheiro fora.
- **Evitar Sobreposição (Desperdício):** Se você compra 2 bolões e eles têm os mesmos números repetidos, você está perdendo a chance de cobrir números novos. A ferramenta calcula a "taxa de sobreposição" para garantir que você compre bolões que se *complementam*.
- **Cercar o Jogo:** O objetivo de cruzar bolões na tela "Análise Comparativa" é encontrar a combinação perfeita de 2 ou 3 bolões de lotéricas diferentes que, juntos, consigam cobrir quase todas as dezenas disponíveis no volante da loteria que você escolheu (seja Mega-Sena, Lotofácil, Dia de Sorte, etc).
- **Encontrar o Melhor Custo-Benefício:** Saber quais lotéricas montaram os bolões mais inteligentes e mais baratos em relação à quantidade de números jogados.

Os dados extraídos (salvos em formato `.json`) são utilizados pelo seu sistema na **Central de Conferências (aba "Bolões" e "Análise Comparativa")**. Isso permite identificar rapidamente as melhores oportunidades de aposta, medindo sobreposição de dezenas e o melhor custo-benefício matemático.

---

## 🛠️ Como extrair os Bolões (2 Métodos)

Você pode extrair os bolões de duas maneiras diferentes:

### Opção 1: Via Interface Web (Servidor Secundário)
A forma mais visual e integrada com a sua tela:
1. Abra um terminal na pasta raiz do seu projeto.
2. Inicie o servidor de extração rodando:
   ```bash
   python servidor_boloes.py
   ```
3. Acesse o seu sistema web normalmente: `http://localhost:5151/central-conferencias`.
4. Navegue até a aba **"Download Bolões"**.
5. Clique para iniciar a extração. O Microsoft Edge abrirá; faça login e deixe o sistema baixar tudo e atualizar a tela em tempo real.

### Opção 2: Via Script no Terminal (Loop Detect)
Um script robusto via terminal que clica nos bolões, pula as páginas e possui um sistema inteligente de detecção de fim-de-página (loop detect):
1. Abra o terminal.
2. Execute o script:
   ```bash
   python conferencias-boloes\script\baixar_boloes-DETECTA-LOOP.py
   ```
3. O Microsoft Edge será aberto. **Faça o login na Caixa** e selecione a loteria desejada (ex: Dia de Sorte).
4. Informe no terminal a **lotérica** (código ou nome, ex: `9833`) e opcionalmente **qtd. de dezenas** (`15` ou Enter = qualquer).
5. Aperte `ENTER` — o script aplica o filtro e inicia a extração.
6. O filtro é **reaplicado a cada página** (a Caixa perde o filtro na paginação).
7. Um JSON por lotérica: `boloes_9833_d15_dia-de-sorte_YYYYMMDD_HHMMSS.json`

---

## 📁 Onde ficam os arquivos?
Independentemente do método escolhido, os arquivos `.json` gerados serão salvos **nesta mesma pasta** (`conferencias-boloes`).

---

## 📊 O que fazer com o arquivo gerado?

Sim! Exatamente na mesma rota que você está: **http://localhost:5151/central-conferencias**

Na barra lateral (ou no menu superior) dessa tela, procure pela aba **"Bolões"** (ou **"Análise de Bolões"**).

Lá dentro você vai encontrar:
- Um botão grande de **Upload** para carregar aquele arquivo `boloes_XXXX.json` que o extrator salvou.
- Assim que você subir o arquivo, o sistema vai listar todas as lotéricas e os bolões que estavam disponíveis no site da Caixa.
- Se você for na aba **"Análise Comparativa de Bolões"** (logo ao lado), você pode selecionar 2 ou mais bolões dessa lista para o sistema cruzar as dezenas e te mostrar a "taxa de sobreposição" (para você não comprar bolões que tenham números muito repetidos entre si e maximizar sua chance de pegar todos os números!).

É só gerar o `.json` pelo extrator e subir nessa aba da Central de Conferências!
