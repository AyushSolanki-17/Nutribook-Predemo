from flask import Flask, render_template, request
from flask_pymongo import PyMongo
from flask import jsonify
import math
import os
import google.generativeai as genai
import os
import json


genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
app = Flask(__name__)
app.config["MONGO_URI"] = os.environ.get('MONGO_URI', "mongodb://localhost:27017/off")
mongo = PyMongo(app)
model = genai.GenerativeModel("gemini-1.5-flash")

@app.route('/')
def index():
    products = list(mongo.db.products1000_top.aggregate([{"$sample": {"size": 25}}]))
    return render_template('index.html', products=products)

@app.route('/products')
def products():
    products = list(mongo.db.products1000_top.find().limit(5))
    return render_template('index.html', products=products)

@app.route('/demo')
def demo():
    return render_template('search.html',)

@app.route('/search')
def search():
    search_query = request.args.get('search', '')

    if search_query != '':

        products = mongo.db.products1000_top.find(
            {"product_name": {"$regex": search_query, "$options": "i"}}
        ).limit(20)

        # Convert the products to a list of dictionaries (JSON format)
        products_list = []
        for product in products:
            image_url = product.get("image_url")
            if image_url is None or (isinstance(image_url, float) and math.isnan(image_url)):
                image_url = "default-image.png"
            categories = product.get("categories", "").split(",")
            categories = [cat.split(":")[-1].strip() for cat in categories if cat != " "]
            products_list.append({
                "code": product["code"],
                "image_url": image_url,  # Default image URL
                "product_name": product.get("product_name", "Unknown Product"),  # Default product name
                "quantity": product.get("quantity", "N/A"),  # Default quantity
                "categories": categories[:3],
                "brand": product.get("brands", "")
            })

        return jsonify(products_list)
    else:
        products = mongo.db.products1000_top.find().limit(10)

        # Convert the products to a list of dictionaries (JSON format)
        products_list = []
        for product in products:
            categories = product.get("categories", "").split(",")
            categories = [cat.split(":")[1].strip() for cat in categories if cat != " "]
            products_list.append({
                "image_url": product.get("image_url") or "default-image.png",  # Default image URL
                "product_name": product.get("product_name", "Unknown Product"),  # Default product name
                "quantity": product.get("quantity", "N/A"),  # Default quantity
                "categories":categories[:3],
                "brand": product.get("brands", "")
            })

        return jsonify(products_list)

def get_user_bio():
    # Fetch the user profile (assuming there's only one document in the collection)
    user_profile = mongo.db.user_profile.find_one()

    # Return the bio if it exists, otherwise return an empty string
    if user_profile and 'bio' in user_profile:
        return """ HERE IS USER PROFILE SUGGEST ACCORDING TO IT \n\n """ + user_profile['bio'] + "\n\n"
    else:
        return ""
    
def generate_gemini_requests(product):
    requests_data = {}
    BASE_PROMPT = '''YOU ARE A PROFESSIONAL NEUTRICIENT AND ENVIRONMENTEALIST respond to these in proper html format and bullet points you are free to use tailwind classes. BUT DONT WRITE FULL HTML START AND END WITH DIV TAGS ONLY; DONT USE MARKDOWN also DONT WRITE ```html or ``` in the response. '''
    PERSONAL_HEALTH = get_user_bio()
    # Nutrients Prompt
    nutrient_prompt = BASE_PROMPT + PERSONAL_HEALTH + (
        "Generate a detailed overview of the nutritional information for the following product, "
        "highlighting its nutrient levels, overall nutriscore, and grade. "
        "Explain how these factors contribute to its health benefits and potential drawbacks."
    )
    nutrient_data = {
        "nutrient_levels": product.get("nutrient_levels"),
        "nutriscore": product.get("nutriscore"),
        "nutriscore_grade": product.get("nutriscore_grade"),
        "nutriments": product.get("nutriments"),
    }
    requests_data["nutrients"] = {
        "prompt": nutrient_prompt,
        "data": nutrient_data
    }

    # Recipes Prompt
    recipe_prompt = BASE_PROMPT + PERSONAL_HEALTH + (
        "Create a collection of recipes based on the product's categories and food groups. "
        "Suggest meal ideas and cooking methods that incorporate these ingredients, "
        "emphasizing their nutritional value and flavor profile."
    )
    recipe_data = {
        "categories": product.get("categories"),
        "food_groups": product.get("food_groups"),
        "food_groups_tags": product.get("food_groups_tags"),
        "ingredients": product.get("ingredients"),
        "product_name": product.get("product_name", "Unknown Product")
    }
    requests_data["recipes"] = {
        "prompt": recipe_prompt,
        "data": recipe_data
    }

    # Ingredients Prompt
    ingredient_prompt = BASE_PROMPT + PERSONAL_HEALTH + (
        "Produce a comprehensive description of the product's ingredients, "
        "including an analysis of their health benefits and any potential allergens. "
        "Discuss how these ingredients work together in culinary applications and their importance in dietary choices."
    )
    ingredient_data = {
        "ingredients": product.get("ingredients"),
        "ingredients_text": product.get("ingredients_text"),
        "ingredient_analysis_tags": product.get("ingredient_analysis_tags"),
        "allergens_from_ingredients": product.get("allergens_from_ingredients"),
    }
    requests_data["ingredients"] = {
        "prompt": ingredient_prompt,
        "data": ingredient_data
    }

    # Environmental Impact Prompt
    environmental_prompt = BASE_PROMPT + (
        "Summarize the environmental impact of the product using its ecoscore data. "
        "Discuss the sustainability practices involved in its production, transportation, and packaging, "
        "as well as the implications of allergens for consumers and the environment."
    )
    environmental_data = {
        "ecoscore_data": product.get("ecoscore_data"),
        "ecoscore_extended_data": product.get("ecoscore_extended_data"),
    }
    requests_data["environmental_impact"] = {
        "prompt": environmental_prompt,
        "data": environmental_data
    }

    return requests_data

def call_gemini_api(data):
    response = model.generate_content(data["prompt"]+" \n\n " +json.dumps(data["data"]))
    # print(response.text)
    return response.text
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": response.text}


def generate_gemini(product):
    requests_data = generate_gemini_requests(product)
    responses = {key: call_gemini_api(value) for key, value in requests_data.items()}

    return jsonify(responses), 200

@app.route('/product/<product_id>')
def get_product(product_id):
    product = mongo.db.products1000_top.find_one({"code": product_id})
    responses = generate_gemini(product)
    print(responses)
    product['responses_gemini_0'] = json.loads(responses[0].data)
    if product:
        return render_template('product.html', product=product)
    else:
        return render_template('search.html', error="Product not found.")

# User profile collection
PROFILE_COLLECTION = 'user_profile'
@app.route('/userprofile', methods=['GET'])
def userprofile():
    return render_template('userprofile.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    profile_collection = mongo.db[PROFILE_COLLECTION]

    if request.method == 'GET':
        profile = profile_collection.find_one()
        if profile:
            return jsonify({
                'name': profile.get('name', ''),
                'bio': profile.get('bio', '')
            })
        else:
            return jsonify({'name': '', 'bio': ''})

    elif request.method == 'POST':
        data = request.json
        name = data.get('name', '')
        bio = data.get('bio', '')
        existing_profile = profile_collection.find_one()
        if existing_profile:
            profile_collection.update_one({'_id': existing_profile['_id']}, {'$set': {'name': name, 'bio': bio}})
        else:
            profile_collection.insert_one({'name': name, 'bio': bio})

        return jsonify({'message': 'Profile saved successfully'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)

