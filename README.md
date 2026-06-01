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
│   │   └── db.py
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
