# 🍳 AI Recipe Assistant

A full-stack AI-powered recipe generation and recommendation system built using:

- ⚡ FastAPI (Backend)
- 🗄 PostgreSQL (Database)
- 🤖 Ollama (Local LLM Runtime)
- 🖼 Unsplash API (Food Images)
- ⚛ React (Frontend)

This project combines deterministic rule-based matching with LLM-powered recipe generation.

---

# 🚀 Features

## ✅ Smart Recipe Matching
- Ingredient-based search
- Match scoring logic
- Primary ingredient filtering
- Threshold-based decision engine

## 🤖 AI Recipe Generation
- Structured JSON output from LLM
- Professional recipe format
- Servings, cooking time, calories
- Sectioned instructions
- Chef-style notes

## 🖼 Dynamic Food Images
- Unsplash API integration
- Image cached in database
- Fallback image support

## 🗄 Database Caching
- Recipes stored in PostgreSQL
- No repeated AI calls
- No repeated Unsplash calls

---

# 📊 Evaluation

20 fixed ingredient sets ([cases.json](Backend/evals/cases.json)) run through recipe generation on `mistral` via Ollama (Apple M3, 16 GB).

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| Valid JSON, first attempt | 95% | 100% |
| Passes schema, first attempt | 95% | 100% |
| Passes schema, with one retry | 100% | 100% |
| Mean ingredient coverage | 97% | 99% |
| Recipes using every requested ingredient | 90% | 95% |
| Latency p50 per case | 26.6s | 33.6s |
| Latency p95 per case | 38.6s | 48.7s |

**How to read this**

- **Coverage** is the share of requested ingredients found in the recipe's ingredient list, using the app's own token matching. It does not check that the instructions use them, or whether the recipe is any good.
- **The matcher undercounts plurals ending in `-es`.** Run 2's only miss was a false negative: the recipe listed `oranges`, which normalizes to `orang` and doesn't match `orange`. A manual review of Run 2's 20 ingredient lists found no false matches.
- **Run 1 is not auditable.** It reported misses for feta and lime, but ingredient lists weren't recorded until Run 2, so they can't be confirmed as real misses.
- **The sample is small.** With 20 cases, each one moves a rate by 5 points, and the model isn't seeded, so results vary between runs. Latency includes retries and excludes the model's cold start.

Per-case detail for Run 2, including each recipe's ingredients, is in [results.json](Backend/evals/results.json). To reproduce, with Ollama running:

```bash
cd Backend
python -m evals.recipe_eval   # overwrites evals/results.json
python -m unittest discover -s tests -t .   # offline tests, no Ollama or database
```

---

# 🧠 Decision Engine

```
User → DB Match?
        ↓ Yes → Return DB
        ↓ No → Generate AI → Fetch Image → Store → Return
```

---

# 🏗 Architecture

```
┌────────────┐
│   React    │
│ Frontend   │
└─────┬──────┘
      │ REST API
      ▼
┌────────────┐
│  FastAPI   │
│  Backend   │
└─────┬──────┘
      │
      ├── Rule-Based Matching Engine
      ├── Ollama LLM Generator
      ├── Unsplash Image Fetch
      └── PostgreSQL Database
```

---

# 📦 Project Structure

```
ai-recipe-assistant/
│
├── Backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── ai.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── ingredients.py
│   │   └── db.py
│   ├── evals/
│   ├── tests/
│   ├── requirements.txt
│   └── .env
│
└── recipe-frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── components/
    │   │   └── RecipeDetail.jsx
    └── package.json
```

---

# ⚙️ Environment Variables

Create a `.env` file inside the `Backend/` folder:

```
UNSPLASH_ACCESS_KEY=your_unsplash_access_key
DATABASE_URL=postgresql://username:password@localhost/dbname
```

---

# 🖥 Local Setup Instructions

---

## 1️⃣ Clone Repository

```bash
git clone <repo-url>
cd ai-recipe-assistant
```

---

## 2️⃣ Install & Start Ollama (Required)

This project uses Ollama to run a local LLM.

### Install Ollama:
👉 https://ollama.com/download

### Pull the required model (example: mistral)

```bash
ollama pull mistral
```

### Start Ollama server

```bash
ollama serve
```

Ollama runs at:

```
http://localhost:11434
```

⚠️ Keep this running in a separate terminal.

---

## 3️⃣ Setup Backend

```bash
cd Backend
python -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

Start FastAPI server:

```bash
uvicorn app.main:app --reload
```

Backend runs at:

```
http://localhost:8000
```

---

## 4️⃣ Setup Frontend

```bash
frr
cd recipe-frontend
npm install
npm run dev
```

Frontend runs at:

```
http://localhost:5173
```

---

# 🔍 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/assistant` | Intelligent recipe endpoint |
| GET | `/recipes` | Fetch stored recipes |
| POST | `/ai/generate-recipe` | Force AI generation |
| GET | `/health` | Health check |

---

# 🧠 Matching Logic

- Convert user ingredients to lowercase set
- Compare with recipe ingredient names
- Calculate match score
- Apply threshold logic
- Use primary ingredient filtering

---

# 🖼 Image Handling

- Search Unsplash API using recipe name
- Store returned image URL
- Fallback image if API fails
- Cached permanently in database

---

# 🛠 Requirements

```
fastapi
uvicorn
sqlalchemy
psycopg2-binary
pydantic
requests
python-dotenv
```

---

# 🚨 Troubleshooting

### ❌ Ollama not running
Error:
```
Connection refused localhost:11434
```
Fix:
```
ollama serve
```

---

### ❌ Model not found
Fix:
```
ollama pull mistral
```

---

### ❌ Unsplash image not loading
- Verify `UNSPLASH_ACCESS_KEY` in `.env`
- Restart backend after editing `.env`

---

### ❌ Database errors
Ensure PostgreSQL is running and `DATABASE_URL` is correct.

---

# 📈 Future Improvements

- User authentication
- Save favorite recipes
- Nutritional analysis
- Cuisine classification
- Docker containerization
- Cloud deployment

---

# 👩‍💻 Author

Full-stack AI system combining deterministic logic with LLM orchestration.

---

# 📜 License

MIT
