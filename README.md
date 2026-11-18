# 🍳 AI Recipe Assistant

A full-stack AI-powered recipe generation and recommendation system built using:

- ⚡ FastAPI (Backend)
- 🗄 PostgreSQL + pgvector (Database and vector search)
- 🤖 Ollama (local models: `mistral` for text, `nomic-embed-text` for embeddings, `llava` for photos)
- 🖼 Unsplash API (Food Images)
- ⚛ React (Frontend)

This project combines deterministic rule-based matching with LLM-powered recipe generation. Where code can do a step reliably (search, scaling, dietary checks, list cleanup), code does it, and the model handles the judgment. Each AI feature has an eval with its numbers below.

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

## 🗓 Meal Planner Agent
- Give it your ingredients and a number of days; it plans one dinner per day that reuses ingredients across days, and ends with one shopping list (what each item is for, shared items first)
- Code does the search, the model does the judgment (`app/meal_planner.py`):
  1. Shortlist stored recipes that fit your dietary filters, ranked by how much of your pantry they use
  2. Try every combination of dinners from the shortlist and keep the 5 best: fewest items to buy, most of your pantry used, most purchases shared across days, no two near-identical dinners
  3. The model picks one of those plans for variety, and may swap in one new dish to use up leftovers, built from your ingredients and the plan's shopping list
  4. Code checks the answer (valid plan, dietary rules, not a near-copy of another dinner, at most one extra purchase) and sends any problems back for one revision
  5. A new dish is written as a full recipe and checked again; if it breaks a filter or needs more than 3 new items, the original dinner stays
  6. The days' shopping lists are merged into one
- The page shows each step the planner took ("How this plan was made")
- If the model is down, it uses the top-ranked plan

## 📷 Ingredients from a Photo
- Upload a photo of your fridge, pantry or counter; a local vision model (`llava` in Ollama) lists the ingredients it sees, and they're added as ingredient tiles like typed ones, ready for recipes, search or the meal planner
- The browser shrinks the photo to 1024px JPEG before upload; nothing is stored
- Code cleans the model's list: plain lowercase names, "a jar of pickles" → "pickles", no containers or vague words ("fridge", "vegetables"), no duplicates ("egg"/"eggs")
- **Check the tiles before cooking:** llava finds under a third of what's in a photo, and a quarter to a third of what it lists isn't there (see the eval below). Remove wrong tiles with ×, type anything it missed
- Set `VISION_MODEL` in `.env` to try a different Ollama vision model

## 👩‍🍳 Cook Mode
- "Cook mode" on any recipe opens a step-by-step view in large type, with the ingredients a tap away
- Times in a step ("simmer for 10-15 minutes", "a minute", "6-7 minutes per side") become timer buttons; ranges time the shorter end, the usual point to start checking. 100 of the 105 stored steps that mention a time get one; the other five say "a few minutes"
- Several timers can run at once and keep going as you move between steps; pause, +1 min or cancel each one. A finished timer beeps, vibrates where supported, and changes the tab title until it's dismissed
- The screen stays on while cook mode is open (Screen Wake Lock API, re-taken when you come back to the tab); the header says when the browser can't do it
- Check off steps as you go; "Done, next step" jumps to the next unchecked one, and checked steps are remembered per recipe in this browser
- Leaving cook mode stops its timers, so the Exit button asks first while any are running. The browser's back button doesn't ask

## ⚖️ Servings & Units
- Drag the servings slider (or tap − / +) and every ingredient amount rescales, in the ingredient list, the shopping list and cook mode
- Kitchen-friendly results: "1 1/2 cups" × 2 → "3 cups", "1 tsp" × 6 → "2 tbsp", "2 tbsp" × 3 → "6 tbsp" (not "3/8 cup"), "3 cloves" ÷ 3 → "1 clove"
- **As written / Metric / US** switch, remembered in this browser. Metric weighs dry goods and keeps liquids in ml; US turns grams back into cups. Small spoon amounts stay as spoons in both
- Grams ↔ cups uses a density table of about 20 common ingredients (flour, sugars, rice, butter, oats, cheese, nuts…), in `src/quantities.js`. Anything not in it converts within its own kind only (ml ↔ cups, g ↔ oz), so 2 cups of grated carrot shows as 470 ml, not grams
- Amounts without a number ("salt to taste", "pinch") are left alone. The step text isn't rewritten, so the directions keep the original amounts, and the page says so

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

## Meal planner

For 8 pantries (some with dietary filters), each method planned 3 dinners. Results are in `Backend/evals/meal_plan_results.json`; run it with `python -m evals.meal_plan_eval`.

| Metric | Best matches (no planning) | Top-ranked plan (search only) | Agent | Fewest purchases |
|--------|------|------|------|------|
| Items to buy | 10.6 | 2.5 | 2.8 | 1.8 |
| Items shared by 2+ dinners | 2.2 | 1.9 | 1.1 | 0.4 |
| Pantry used | 72% | 48% | **77%** | 45% |
| Near-identical dinner pairs | 0 | 0 | 0 | 0 |

Agent: 8/8 valid plans (3 distinct dinners that meet the filters), 7 new dishes, 2 revisions, p50 latency 28s.

- **Best matches** picks the 3 recipes that use the most of the pantry, independently. They often need a whole spice cupboard each, so it buys about 4 times as much.
- **Fewest purchases** is a lower bound on shopping, but it gets there by choosing dishes that use less than half the pantry.
- **The agent** buys almost as little as the search alone and uses the most of the pantry, mostly through the new dish it adds for leftovers (it added one in 7 of 8 plans). It shares fewer purchases than the search's top plan, because the new dish usually replaces a dinner that shared one.
- **First version:** the model built the plan itself from a list of recipes. It bought 8.0 items per plan, shared 0.6, and once planned "Indian Corn Khichdi" and "Indian Corn Kichdi" together. Moving the search into code fixed both and halved the latency.
- **Limits:** variety depends on the stored recipes, and with about 60 distinct dishes, plans still repeat a main ingredient ("Carrot Soup" with "Carrot Side Dish"). "Vegetable oil" counts as a purchase, which made the model's tofu stir-fry fail the extra-items check twice.

## Ingredients from a photo

17 Unsplash photos, hand-labeled in `Backend/evals/photo_cases.json`: 6 fridges, 2 pantry shelves, 3 counters, 5 grocery spreads and a nearly empty fridge (98 clearly visible ingredients in all). An ingredient counts as found if the model names it or a close variant ("red onion" for onion). A listed item counts as invented if it's not in the photo; reasonable broader answers ("herbs" for parsley) are allowed.

| Prompt (`llava` 7B) | Found | Listed items that are right | Items listed per photo | Invented for the nearly empty fridge | p50 latency |
|--------|------|------|------|------|------|
| **JSON list (used)** | 28–29% | 66–75% | 3–4 | 1 ("pickles") | 6s |
| Free-text list | 45% | 55% | 8.9 | 4 (eggs, red bell pepper, milk, chicken) | 6.5s |
| Describe the photo, then `mistral` extracts the list | 47% | 54% | 8.5 | 2 (ketchup, eggs) | 47s |

Ranges are two runs of the same prompt. Results for the used prompt are in `Backend/evals/photo_results.json`.

- **The model is the limit, not the prompt.** Every prompt tops out under half found, with half of the extra items wrong. llava falls back on what fridges usually hold: it listed milk, cheese, butter and sausages for a fridge of kale, strawberries and herbs, and found nothing in either pantry photo of labeled jars.
- **The JSON prompt is used because it invents the least.** Invented ingredients go straight into recipes and plans; a missed one costs a few keystrokes. The free-text prompts would add four ingredients to a fridge holding three drinks.
- **It does best on loose produce in good light:** 75% found on a market shelf, and the broccoli photo was perfect. Packaged and jarred food mostly goes unnamed.
- **A free-text llava call once repeated itself until the 5-minute timeout**, so output is now capped at 300 tokens.
- **Next step:** a stronger vision model (`VISION_MODEL=...`); the eval measures any of them on the same photos.

## Running the evals

With Ollama running, from `Backend/`:

```bash
python -m evals.recipe_eval     # generation; 20 cases, writes evals/results.json
python -m evals.search_eval     # retrieval; reads the database only, writes evals/search_results.json
python -m evals.rag_eval        # RAG generation; ~20 model calls (10–20 min), writes evals/rag_results.json
python -m evals.meal_plan_eval  # planner; 8 plans (~5 min), writes evals/meal_plan_results.json
python -m evals.photo_eval      # photo ingredients; 17 photos (~2 min), writes evals/photo_results.json
```

None of them write to the database. The unit tests need neither Ollama nor a database: `python -m unittest discover -s tests -t .`

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
      ├── Rule-based matching, dietary checks, scaling, shopping lists   (code)
      ├── Hybrid search: pgvector embeddings + Postgres full-text        (nomic-embed-text)
      ├── Recipe generation, RAG, refinement, substitutions             (mistral)
      ├── Meal planner: code searches plans, model chooses              (mistral)
      ├── Ingredients from a photo                                      (llava)
      ├── Unsplash image fetch
      └── PostgreSQL database
```

---

# 📦 Project Structure

```
ai-recipe-assistant/
│
├── Backend/
│   ├── app/
│   │   ├── main.py             # API endpoints
│   │   ├── ai.py               # model prompts and calls (Ollama)
│   │   ├── models.py           # database tables
│   │   ├── schemas.py          # request/response and model-output contracts
│   │   ├── db.py
│   │   ├── ingredients.py      # ingredient name matching
│   │   ├── dietary.py          # dietary filters and tags
│   │   ├── shopping.py         # shopping lists
│   │   ├── substitutions.py    # hand-picked ingredient swaps
│   │   ├── embeddings.py       # nomic-embed-text calls
│   │   ├── semantic_search.py  # hybrid craving search
│   │   ├── index_recipes.py    # re-embed recipes
│   │   ├── scaling.py          # servings scaling for refinements
│   │   ├── meal_planner.py     # meal-planner agent
│   │   └── photo.py            # photo checks and ingredient-list cleanup
│   ├── evals/                  # evals, labeled cases and results
│   ├── tests/
│   ├── requirements.txt
│   └── .env
│
└── recipe-frontend/
    ├── src/
    │   ├── App.jsx             # pages and routing
    │   ├── components/         # RecipeDetail, RefinePanel, MealPlanPage, PhotoIngredients,
    │   │                       # ShoppingList, DietaryFilters
    │   ├── savedRecipes.js     # favorites and history (browser storage)
    │   └── dietary.js
    └── package.json
```

---

# ⚙️ Environment Variables

Create a `.env` file inside the `Backend/` folder:

```
UNSPLASH_ACCESS_KEY=your_unsplash_access_key
DATABASE_URL=postgresql://username:password@localhost/dbname
VISION_MODEL=llava   # optional; any Ollama vision model for ingredients from a photo
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

### Pull the models

```bash
ollama pull mistral
ollama pull nomic-embed-text   # embeddings for craving search
ollama pull llava              # vision model for ingredients from a photo (~4.7 GB, optional)
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
cd recipe-frontend
npm install
npm run dev
npm test   # quantity scaling and unit conversion (Node's built-in test runner)
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
| POST | `/ingredients/from-photo` | List the ingredients in a fridge/pantry photo (`image`: base64 JPEG/PNG or data URL, 5 MB max) |
| POST | `/meal-plan` | Plan dinners for 1–7 days (`ingredients`, `days`, optional `filters`) with one shopping list |
| POST | `/recipes/{id}/refine` | Apply a change (`{"instruction": "spicier"}`), saved as a new recipe |
| POST | `/ai/generate-recipe` | Force AI generation |
| POST | `/recipes` | Save a recipe |
| POST | `/recipes/search` | Stored recipes matching a list of ingredients |
| GET | `/ingredient-image?name=` | Photo for an ingredient tile (cached) |
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

Python 3.11, Node 20.19+ (for Vite 7), PostgreSQL with the pgvector extension, and Ollama. Python packages are pinned in `Backend/requirements.txt`:

```
fastapi
uvicorn
sqlalchemy
psycopg2-binary
pgvector
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
Fix: pull the model the feature uses.
```
ollama pull mistral            # recipes, search generation, meal planner
ollama pull nomic-embed-text   # craving search
ollama pull llava              # ingredients from a photo
```

---

### ❌ "Couldn't read the photo"
- Check that `llava` (or your `VISION_MODEL`) is pulled and Ollama is running
- The first photo after starting Ollama is slower while the model loads
- Uploads must be JPEG or PNG and at most 5 MB; the frontend converts and shrinks photos automatically

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
