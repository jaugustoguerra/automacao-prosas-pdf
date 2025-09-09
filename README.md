# 📝 Automação de Extração e Download de Anexos em PDFs

## 📌 Sobre o Projeto
Este projeto nasceu de uma necessidade real no trabalho: baixar anexos de **PDFs com links temporários (S3)**.  
Cada PDF continha informações de proposta e anexos hospedados em links que **expiravam em 1 hora**.  
Com milhares de arquivos para processar manualmente, a solução foi criar uma **automação em Python**.

No total, o script processou:
- **+10.000 PDFs lidos**
- **+4.500 anexos encontrados e baixados automaticamente**

---

## ⚡ Funcionalidades
- Leitura recursiva de todas as pastas e PDFs
- Extração de links dentro dos PDFs (inclusive links “escondidos” no texto)
- Download automático dos anexos diretamente nas pastas dos PDFs
- Tratamento de:
  - **links temporários do S3**
  - **nomes de arquivos longos** (truncamento automático para evitar erro do Windows)
  - **caracteres inválidos em nomes de arquivos**
  - **limite de path no Windows (MAX_PATH)** com suporte a `\\?\`
- Estratégia de **retries** para evitar falhas de rede
- Resumo final com estatísticas: PDFs processados, links encontrados, anexos baixados/ignorados/falhos

---

## 🛠️ Tecnologias Utilizadas
- [Python 3.x](https://www.python.org/)
- [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/en/latest/) → leitura e parsing de PDFs
- [Requests](https://docs.python-requests.org/) → download de arquivos
- Regex (expressões regulares) → extração de links
- Manipulação de caminhos → para lidar com restrições do Windows

---

## 🚀 Como Usar

1. Clone este repositório ou copie o script.
2. Instale as dependências:
   ```bash
   pip install requests PyMuPDF
   ```
3. Configure o caminho da pasta raiz no script:
   ```python
   PASTA_RAIZ_PROPOSTAS = r'C:\Users\SeuUsuario\Downloads\Propostas'
   ```
4. Execute o script:
   ```bash
   python extrair_anexos.py
   ```

---

## 📂 Estrutura esperada
```
Propostas/
│
├── Proposta-001/
│   └── proposta_recursos.pdf
│
├── Proposta-002/
│   └── proposta_recursos.pdf
│
└── ...
```

Os anexos serão salvos diretamente nas mesmas pastas dos PDFs.

---

## 📊 Exemplo de Saída
```
Processando PDF: Proposta-001/proposta_recursos.pdf
  -> Projeto: Nome do Projeto | ID: 123456
  -> 3 link(s) encontrados. Iniciando downloads...
    ✅ Salvo: Anexo1.pdf
    ✅ Salvo: Anexo2.pdf
    - Ignorado (já existe): Anexo3.pdf

--- RESUMO ---
PDFs processados: 10000
Links encontrados: 4500
Arquivos baixados: 4300
Ignorados: 200
Falhas: 0
--- FIM ---
```

---

## 💡 Desafios enfrentados
- Links temporários do S3 → expiram em 1h, exigindo automação rápida.
- PDFs com **assinaturas digitais** → geravam nomes de arquivos extremamente longos.
- Restrição do Windows (`MAX_PATH`) → necessidade de truncar nomes e usar `\\?\`.
- Alto volume de dados → otimização para processar milhares de PDFs sem travar.

---

## 🏆 Resultado
- Processo que seria **inviável manualmente** foi concluído em poucas horas.
- Mais de **4.500 anexos** foram baixados com sucesso.
- Automação tornou o processo **seguro, repetível e escalável**.

---

## ✨ Autor
**José Augusto Guerra da Silva**  
📌 Analista de Sistemas | DBA | Entusiasta de Automação e Engenharia de Dados  
