# The same failing call, before and after

**Question (identical in both runs):** I have 1 kg of white cabbage. How much fine sea salt do I need for the caraway sauerkraut?

The model's mistake is the same in both: it scales the recipe so that the *salt*
weighs 1 kg, rather than the cabbage. What changes is whether the tool lets that
mistake through silently.

## BEFORE

*recipe_server_v1.py: three-word docstrings, "Error 3"*

```
step 1  THINK   I need to find the recipe for caraway sauerkraut to determine the amount of fine sea salt required.
        ACT     search_recipes({"query": "caraway sauerkraut"})
        RESULT  {"results": [{"recipe_id": "R-106", "title": "Small-Batch Caraway Sauerkraut", "dietary_tags": ["vegan", "gluten-free", "dairy-free", "nut-free"]}, {"recipe_id": "R-102", "title": "One Hundred Percent Wholegrain Rye Sourdough", "dietary_tags": ["vegan", "dairy-free", "contains-gluten"]}]}
step 2  THINK   I found two recipes, but they don't match the task. I need to find the specific recipe for caraway sauerkraut and then scale the recipe to find the amount of fine sea salt needed.
        ACT     get_recipe_section({"recipe_id": "R-106", "section": "ingredients"})
        RESULT  {"recipe_id": "R-106", "title": "Small-Batch Caraway Sauerkraut", "section": "Ingredients", "text": "| Ingredient | Weight | % of Base |\n|---|---|---|\n| White cabbage, finely shredded | 350 g | 100% |\n| Fine sea salt | 7 g | 2% |\n| Caraway seed | 2 g | 0.6% |\n| Juniper berries, cracked | 1 g | 0.3% |\n| Total | 360 g | 102.9% |"}
step 3  THINK   I found the ingredients list for the caraway sauerkraut recipe. Now I need to scale the recipe to find out how much fine sea salt is needed for 1 kg of white cabbage.
        ACT     scale_recipe({"recipe_id": "R-106", "ingredient": "Fine sea salt", "target_grams": 1000})
        RESULT  {"recipe_id": "R-106", "title": "Small-Batch Caraway Sauerkraut", "scaled_so_that": "Fine sea salt = 1000 g (card says 7.0 g)", "factor": 142.857, "scaled_ingredients": ["White cabbage, finely shredded: 50000 g", "Fine sea salt: 1000 g", "Caraway seed: 286 g", "Juniper berries, cracked: 143 g"]}
step 4  FINAL   You need 2 kg of fine sea salt for 1 kg of white cabbage in the caraway sauerkraut recipe.
```

- **Final answer:** You need 2 kg of fine sea salt for 1 kg of white cabbage in the caraway sauerkraut recipe.
- **Correct (20 g of salt for 1 kg of cabbage)?** NO
- model calls: 4 · 75s · status: finished

## AFTER

*recipe_server.py: docstring written as a prompt, recoverable errors*

```
step 1  THINK   The user wants to know how much fine sea salt is needed for 1 kg of white cabbage in the caraway sauerkraut recipe.
        ACT     search_recipes({"query": "caraway sauerkraut", "dietary_tag": "none"})
        RESULT  {"results": [], "hint": "Nothing matched 'caraway sauerkraut' with tag 'none'. Tags in use: contains-dairy, contains-egg, contains-fish, contains-gluten, contains-sesame, contains-shellfish, dairy-free, gluten-free, nut-free, vegan, vegetarian."}
step 2  THINK   The search did not find a recipe matching the query 'caraway sauerkraut' with the dietary tag 'none'. I will now filter the results for 'caraway sauerkraut' with the 'vegan' tag.
        ACT     search_recipes({"query": "caraway sauerkraut", "dietary_tag": "vegan"})
        RESULT  {"results": [{"recipe_id": "R-106", "title": "Small-Batch Caraway Sauerkraut", "dietary_tags": ["vegan", "gluten-free", "dairy-free", "nut-free"]}, {"recipe_id": "R-102", "title": "One Hundred Percent Wholegrain Rye Sourdough", "dietary_tags": ["vegan", "dairy-free", "contains-gluten"]}]}
step 3  THINK   The search found two recipes with 'caraway sauerkraut' and 'vegan' tags. I will now get the recipe section for 'R-106' to find the amount of fine sea salt needed for 1 kg of white cabbage.
        ACT     get_recipe_section({"recipe_id": "R-106", "section": "ingredients"})
        RESULT  {"recipe_id": "R-106", "title": "Small-Batch Caraway Sauerkraut", "section": "Ingredients", "text": "| Ingredient | Weight | % of Base |\n|---|---|---|\n| White cabbage, finely shredded | 350 g | 100% |\n| Fine sea salt | 7 g | 2% |\n| Caraway seed | 2 g | 0.6% |\n| Juniper berries, cracked | 1 g | 0.3% |\n| Total | 360 g | 102.9% |"}
step 4  THINK   The ingredients list shows that for 350g of white cabbage, 7g of fine sea salt is needed. I will now scale the recipe to find out how much salt is needed for 1 kg of cabbage.
        ACT     scale_recipe({"recipe_id": "R-106", "ingredient": "white cabbage", "target_grams": 1000})
        RESULT  {"recipe_id": "R-106", "title": "Small-Batch Caraway Sauerkraut", "scaled_so_that": "White cabbage, finely shredded = 1000 g (card says 350 g)", "factor": 2.857, "scaled_ingredients": ["White cabbage, finely shredded: 1000 g", "Fine sea salt: 20 g", "Caraway seed: 5.7 g", "Juniper berries, cracked: 2.9 g"]}
step 5  FINAL   For 1 kg of white cabbage, you need 20g of fine sea salt.
```

- **Final answer:** For 1 kg of white cabbage, you need 20g of fine sea salt.
- **Correct (20 g of salt for 1 kg of cabbage)?** YES
- model calls: 5 · 108s · status: finished

## What actually changed

1. **The docstring is now a prompt.** It says target_grams applies to the ingredient you
   name, tells the model to pass the ingredient the cook *has* (the cabbage), and spells
   out the trap: scaling by the salt multiplies the recipe by 143.
2. **The error path is recoverable.** When a scale looks absurd the tool no longer returns
   a number like `Error 3`, or worse a confident wrong answer. It returns what went wrong,
   which ingredient was probably meant, and the exact call to make next:

   ```json
   {"warning": "Scaling Small-Batch Caraway Sauerkraut so that 'Fine sea salt' weighs 1000 g
                multiplies the whole recipe by 143x, which is almost certainly not what was meant.",
    "likely_intended": "The cook probably has 1000 g of 'White cabbage, finely shredded'…",
    "next_step": "Call scale_recipe('R-106', 'White cabbage, finely shredded', 1000) and read
                  the figure for 'Fine sea salt' out of the result."}
   ```

   Note what it is *not*: it is not a protocol error. The call succeeded; the tool is
   telling the model something it can act on. A thrown exception would have ended the run.

## The same bad calls at the tool level (no model involved)

The improved docstring stopped the model making the mistake at all, so the new error
path never fired in the transcript above. Here are the identical calls sent straight
to each server:

### `scale_recipe({"recipe_id": "R-106", "ingredient": "fine sea salt", "target_grams": 1000})`
*scale by the salt instead of the cabbage (what the model actually did)*

| server | what comes back |
|---|---|
| BEFORE | `{"recipe_id": "R-106", "title": "Small-Batch Caraway Sauerkraut", "scaled_so_that": "Fine sea salt = 1000 g (card says 7.0 g)", "factor": 142.857, "scaled_ingredients": ["White cabbage, finely shredded: 50000 g", "Fine sea salt: 1000 g", "Caraway seed: 286 g", "Juniper berries, cracked: 143 g"]}` |
| AFTER | `{"warning": "Scaling Small-Batch Caraway Sauerkraut so that 'Fine sea salt' weighs 1000 g multiplies the whole recipe by 143x, which is almost certainly not what was meant.", "likely_intended": "The cook probably has 1000 g of 'White cabbage, finely shredded', the main ingredient (the card uses 350 g of it).", "next_step": "Call scale_recipe('R-106', 'White cabbage, finely shredded', 1000) and rea` |

### `scale_recipe({"recipe_id": "R-106", "ingredient": "chocolate", "target_grams": 100})`
*an ingredient that isn't in the recipe*

| server | what comes back |
|---|---|
| BEFORE | `{"error": "Error 3"}` |
| AFTER | `{"error": "No ingredient matching 'chocolate' in Small-Batch Caraway Sauerkraut (R-106).", "ingredients_in_this_recipe": ["White cabbage, finely shredded", "Fine sea salt", "Caraway seed", "Juniper berries, cracked"], "next_step": "Call scale_recipe again with one of the ingredient names listed above, exactly as written."}` |

### `get_recipe_section({"recipe_id": "R-106", "section": "nutrition"})`
*a section that doesn't exist*

| server | what comes back |
|---|---|
| BEFORE | `{"error": "Error 4"}` |
| AFTER | `{"error": "'nutrition' is not a section. Use one of: ingredients, method, allergens, storage, about."}` |

**The difference that matters:** `Error 3` gives the model nothing to act on, so it
either gives up or invents an answer. The rewritten version names the problem, lists
what does exist, and gives the exact call to make next — so the model can fix itself
inside the same run.

