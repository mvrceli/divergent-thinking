# Word Association Game — Divergent Thinking

A human–AI word association game that measures divergent thinking using Word2Vec cosine similarity.

## Setup

```bash
# 1. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the server
python backend/app.py

# 4. Run Ollama
# Listening on "http://localhost:11434/api/generate"
# Model "llama3.2:latest"  
ollama serve
```

On first launch, gensim will download the `word2vec-google-news-300` model (~1.7 GB). This is cached for subsequent runs.

Open **http://localhost:5001** in your browser to play.




