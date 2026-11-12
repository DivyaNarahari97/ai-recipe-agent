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

## 🔎 Craving Search
- Search by what you feel like eating ("something light and spicy for a cold night"), not just ingredients
- Hybrid retrieval: `nomic-embed-text` embeddings in pgvector (HNSW cosine index) plus Postgres full-text search (GIN index), merged with reciprocal rank fusion
- "Create a new recipe from these" generates a new recipe from the craving with the top 3 matches as context (RAG), and shows which recipes inspired it
- Each recipe's embedded text includes derived words ("light", "quick", "spicy"), because an embedding can't infer them from numbers like "250 kcal"
- Unindexed recipes are embedded on the next search; `python -m app.index_recipes` re-embeds recipes whose text or model changed
- Works with the dietary filters, and returns one result per recipe name

## 💬 Change a Recipe
- On any recipe, ask for a change ("make it for 6 people", "spicier", "no oven") and the model edits that recipe instead of generating a new one
- Changes build on each other, with undo; each version is saved as a new recipe, so the original and any saved copies stay as they were
- Servings are scaled in code, not by the model: in testing, `mistral` updated the servings but left the quantities unchanged, or scaled them by the wrong factor
- If the model returns the recipe unchanged, it's asked once more before the request fails

## 🥗 Dietary Filters
- Vegetarian, vegan and gluten-free, plus max time and max calories
- Applied to stored recipes during matching and added to the generation prompt
- Generated recipes that break a filter are saved but not shown for that search
- Rule-based checks on ingredient names (`app/dietary.py`), so they work on recipes saved before filters existed. They only see the ingredient list, so a recipe that leaves out an ingredient (such as a taco recipe with no tortilla) can be mis-tagged.

## 🛒 Shopping List
- Builds a list from a recipe, leaving out the ingredients you picked
- Salt, pepper and water are listed separately as pantry staples
- Tick items off and copy the list

## 🔁 Substitutions & Cuisine
- "Missing this?" on each ingredient: hand-picked swaps, with an LLM fallback that's cached
- Recipes are tagged with a cuisine and can be browsed by it

## ❤️ Favorites & History
- Save recipes and see recently viewed ones
- Stored in the browser (no account needed), so they don't sync across devices

## 🗄 Database Caching
- Recipes stored in PostgreSQL
- No repeated AI calls
- No repeated Unsplash calls

---

# 📊 Evaluation

20 fixed ingredient sets ([cases.json](Backend/evals/cases.json)) run through recipe generation on `mistral` via Ollama (Apple M3, 16 GB).

| Metric | Run 1 | Run 2 | Run 3 |
|--------|-------|-------|-------|
| Valid JSON, first attempt | 95% | 100% | 100% |
| Passes schema, first attempt | 95% | 100% | 100% |
| Passes schema, with one retry | 100% | 100% | 100% |
| Mean ingredient coverage | 97% | 99% | 99% |
| Recipes using every requested ingredient | 90% | 95% | 95% |
| Tagged with a named cuisine | – | – | 65% |
| Latency p50 per case | 26.6s | 33.6s | 20.5s |
| Latency p95 per case | 38.6s | 48.7s | 26.0s |

Run 3 uses the current prompt, which also asks for a `cuisine` from a fixed list. Runs 1–2 predate that field.

**How to read this**

- **Coverage** is the share of requested ingredients found in the recipe's ingredient list, using the app's own token matching. It does not check that the instructions use them, or whether the recipe is any good.
- **The matcher undercounts plurals ending in `-es`.** The only miss in both Run 2 and Run 3 was the same false negative: the recipe listed `oranges`, which normalizes to `orang` and doesn't match `orange`. A manual review of Run 2's 20 ingredient lists found no false matches.
- **Cuisine tagging** counts recipes that got a named cuisine rather than the `Other` fallback. The 7 untagged recipes in Run 3 include both stir-fries. The eval doesn't record the model's raw label, so it can't distinguish an explicit `Other` from an off-list label like `Asian` that was mapped to `Other`.
- **Run 1 is not auditable.** It reported misses for feta and lime, but ingredient lists weren't recorded until Run 2, so they can't be confirmed as real misses.
- **The sample is small.** With 20 cases, each one moves a rate by 5 points, and the model isn't seeded, so results vary between runs. Latency includes retries and excludes the model's cold start.

Per-case detail for Run 3, including each recipe's ingredients and cuisine, is in [results.json](Backend/evals/results.json). To reproduce, with Ollama running:

```bash
cd Backend
python -m evals.recipe_eval   # overwrites evals/results.json
python -m unittest discover -s tests -t .   # offline tests, no Ollama or database
```

## Craving search (retrieval)

10 craving queries over the 79 stored recipes (56 distinct names). Relevance is decided by a rule for each query (for example, "light" means at most 350 kcal), so the eval needs no hand labels. "Random pick" is the share of recipes that are relevant, which is what picking at random would score.

- **Vector:** cosine similarity on `nomic-embed-text` embeddings.
- **Keyword:** Postgres full-text search.
- **Hybrid:** both, merged with reciprocal rank fusion. This is what `/search` uses.

| Query | Random pick | Vector P@5 | Keyword P@5 | Hybrid P@5 |
|-------|------|------|------|------|
| something light for lunch | 75% | 80% | 100% | 100% |
| a quick snack I can make in a few minutes | 23% | 20% | 60% | 60% |
| something with a spicy kick | 21% | 100% | 100% | 100% |
| a plant-based meal without any animal products | 66% | 80% | 80% | 80% |
| creamy, cheesy comfort food | 16% | 40% | 40% | 60% |
| a warming Indian curry | 20% | 80% | 60% | 100% |
| something with chicken | 7% | 80% | 80% | 80% |
| a fresh crunchy salad | 12% | 60% | 80% | 80% |
| something sweet for dessert | 7% | 40% | 20% | 40% |
| light and spicy for a cold night | 14% | 20% | 60% | 60% |
| **Mean** | **26%** | **60%** | **68%** | **76%** |

**One recipe matching everything:** with vector search alone, "Indian Corn Pakoda" appeared in the top 5 for 9 of 10 queries, including dessert. That's a known embedding problem called hubness. Hybrid search cuts it to 6 of 10, which is better but not solved; a reranker would be the next thing to try.

**What the eval changed**

- **Keyword search was added.** Hybrid search beats either method alone on mean precision, and is never worse than vector search on any query.
- **Duplicates were crowding results.** One dish was stored 6 times. Search and the eval now keep one result per recipe name, which raised precision on every variant tried.
- **Style words help.** Adding derived words ("light", "quick", "spicy") to the embedded text raised vector precision from 54% to 60% in an earlier run.
- **Shorter documents didn't help.** Dropping the steps or notes from the embedded text made no difference.
- **Spicy dishes were being missed.** Building the eval exposed a plural bug (`chillies` normalized to `chilly`) that kept dishes with green chillies from being tagged spicy.

**Limits**

- **Some numbers are partly circular.** The style words and the "light", "quick" and "spicy" relevance rules share thresholds, so those rows partly measure whether the derived word was retrieved.
- **The sample is small.** 10 queries over a library dominated by corn and Indian dishes means single-query differences are noise.

## Recipes from craving search (RAG)

For the same 10 cravings, `mistral` generated one recipe with the top 3 hybrid-search matches in the prompt, as `/search/generate` does, and one recipe from the craving alone.

| Metric | Without retrieval | With retrieval (RAG) |
|--------|------|------|
| Produced a recipe (one retry allowed) | 80% | 90% |
| Meets the craving | 75% | 78% |
| Ingredient overlap with retrieved recipes | 14% | 56% |
| Copies a retrieved recipe | 0% | 11% |
| Latency p50 | 57.0s | 66.3s |

**How to read this**

- **Retrieval clearly grounds the output.** With context, 56% of a recipe's ingredient words come from the retrieved recipes, versus 14% by chance. For "something sweet for dessert", the model went from chocolate mousse tartlets to carrot and corn dumplings built entirely from the library.
- **It barely changes whether the craving is met.** 78% versus 75% is one recipe out of 10; Mistral meets most cravings either way. Rules on time and calories use the model's own estimates.
- **One recipe was too close to its source.** The "Indian curry" recipe shared 70% or more of its ingredients with a retrieved recipe, even though the prompt says not to copy. `/search/generate` now rejects recipes like that and tries once more.
- **All 3 failures were timeouts, not bad output.** The model call hit its 120-second limit, since responses to craving prompts can run long on a laptop. The limit is now 300 seconds. Latency includes the timeouts.
- **These numbers were measured before both fixes**, so the eval hasn't been rerun with them.

```bash
cd Backend
python -m evals.search_eval   # retrieval; reads the database only, writes evals/search_results.json
python -m evals.rag_eval      # generation; ~20 model calls (10–20 min), writes evals/rag_results.json
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
ollama pull nomic-embed-text   # embeddings for craving search
```

Craving search also needs the [pgvector](https://github.com/pgvector/pgvector) extension in Postgres (`brew install pgvector` on macOS). The backend runs `CREATE EXTENSION IF NOT EXISTS vector` on startup. Without the extension, everything except `/search` still works.

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
| POST | `/assistant` | Intelligent recipe endpoint (optional `filters`) |
| GET | `/recipes` | Fetch stored recipes (optional `?cuisine=`) |
| POST | `/search` | Hybrid search by craving (optional `filters`) |
| POST | `/search/generate` | New recipe from a craving, grounded in the top matches |
| GET | `/cuisines` | Cuisines with recipe counts |
| GET | `/substitutions?ingredient=` | Substitutes for an ingredient |
| POST | `/recipes/{id}/shopping-list` | Split ingredients into need / have / staples |
| POST | `/recipes/{id}/refine` | Apply a change (`{"instruction": "spicier"}`), saved as a new recipe |
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
- Nutritional analysis
- Docker containerization
- Cloud deployment

---

# 👩‍💻 Author

Full-stack AI system combining deterministic logic with LLM orchestration.

---

# 📜 License

MIT
