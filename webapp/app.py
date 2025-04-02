import os
import psycopg2
from flask import Flask, request, jsonify, render_template # Import render_template
from google.cloud import storage
import logging
from google import auth

from google import genai
from google.genai.types import EmbedContentConfig

# Configure logging (moved to top for consistent logging)
logging.basicConfig(level=logging.DEBUG)  # Set the default log level
logger = logging.getLogger(__name__)  # Get a logger for this module

app = Flask(__name__)  # Flask automatically looks for templates/ and static/

# Configuration
DB_HOST = os.environ.get('DB_HOST_PROXY')
DB_NAME = os.environ.get('DB_NAME')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
BUCKET_NAME = os.environ.get('BUCKET_NAME')

PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT')
region = "us-central1"
MODEL_NAME_EMBEDDING = "text-embedding-005" # Change based on SDK
MODEL_NAME_LLM = "gemini-2.0-flash"

credentials=None

# Storage Client Init (keep as before)
try:
    credentials, project = auth.default(
        #     scopes=SCOPES
        )
    credentials.refresh(auth.transport.requests.Request())
    storage_client = storage.Client(credentials=credentials)
    logger.info("Storage client initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize storage client: {e}")
    storage_client = None

# DB Connection function (keep as before)
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=5432, # Use DB_PORT env var if set, else 5432
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
            )
        # logging.info("Database connection successful.")
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        return None

# Signed URL function (keep as before)
def get_signed_url(pokemon_name):

    if not storage_client:
        logger.error("Storage client not available for generating signed URL.")
        return None
    try:
        blob_name = f"images/{pokemon_name.lower()}.png"
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(blob_name)
        if not blob.exists():
             logger.warning(f"Image blob not found: gs://{BUCKET_NAME}/{blob_name}")
             # Return placeholder or None - Using placeholder defined in HTML/CSS now
             return None # Let template handle missing image
        
        

        
        url = blob.generate_signed_url(version="v4", expiration=900, service_account_email=credentials.service_account_email,
    access_token=credentials.token, )
        # logger.info(f"Generated signed URL for {blob_name}")
        return url
    except Exception as e:
        logger.error(f"Error generating signed URL for {pokemon_name} (blob: {blob_name}): {e}")
        return None



def generate_embedding_app(text):
     if not text: return None
     try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=region)
        response = client.models.embed_content(
            model=MODEL_NAME_EMBEDDING,
            contents=[
                text,
            ],
            config=EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",  # Optional
                output_dimensionality=768,  # Optional
            ),
        )
        return response.embeddings[0].values
     except Exception as e:
         logger.error(f"App: Failed to get GenAI embedding: {e}", exc_info=True)
         return None

def call_llm_to_choose_genai(user_query, top_pokemon_list):
    """Uses Gemini via GenAI SDK to choose the best Pokemon."""
    if not top_pokemon_list:
        logger.warning("No top Pokemon provided to LLM.")
        return None

    # --- Prompt Engineering ---
    prompt = f"""You are a helpful Pokémon expert assistant.
                A user is looking for a starter Pokémon and has provided the following request:
                User Request: "{user_query}"

                Based on their request, a search found the following top 3 potential matches:
            """
    for i, pokemon in enumerate(top_pokemon_list):
        prompt += f"\n{i+1}. {pokemon['name']}:\n   Description: {pokemon['description']}\n---"

    prompt += f"""
                Analyze the user's request ("{user_query}") and the descriptions of the 3 Pokémon provided.
                Determine which *single* Pokémon from the list ({', '.join([p['name'] for p in top_pokemon_list])}) is the *best fit* for the user's request.

                Your Response Format:
                1. First line: ONLY the name of the recommended Pokémon.
                2. Subsequent lines: A brief explanation (2-3 sentences) of *why* you recommend that specific Pokémon, referencing the user's request and the Pokémon's description. Example:
                Pikachu
                Because you asked for something fast and electric, Pikachu fits perfectly with its speed and electric shocks.
            """
    # --- End Prompt ---

    try:
        # Create client and model instance (relies on ADC)
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=region)

        logger.info(f"Sending prompt to LLM {MODEL_NAME_LLM} for query: '{user_query}'")
        
        response: GenerateContentResponse = client.models.generate_content(
            model=MODEL_NAME_LLM,
            contents=prompt,
        )

        if response.candidates and response.candidates[0].content.parts:
            llm_text = response.text # .text provides convenience access
            logger.info(f"LLM Response received:\n{llm_text}")

            lines = llm_text.strip().split('\n', 1)
            recommended_name = lines[0].strip()
            explanation = lines[1].strip() if len(lines) > 1 else "This Pokémon seems like a good match for your request."

            valid_names = [p['name'] for p in top_pokemon_list]
            if recommended_name not in valid_names:
                logger.warning(f"LLM recommended '{recommended_name}', which was not in the top 3 options {valid_names}. Falling back.")
                first_match = top_pokemon_list[0]
                return {
                    'name': first_match['name'],
                    'explanation': f"Based on similarity, {first_match['name']} seems like a good starting point."
                }

            return {'name': recommended_name, 'explanation': explanation}
        else:
            logger.warning(f"LLM returned an empty or invalid response for query: {user_query}")
            logger.warning(f"LLM Raw Response: {response}")
            # Fallback: Return the first Pokemon from the vector search
            first_match = top_pokemon_list[0]
            return {
                'name': first_match['name'],
                'explanation': f"Based on similarity, {first_match['name']} seems like a good starting point."
            }

    except Exception as e:
        logger.error(f"Error calling LLM ({MODEL_NAME_LLM}): {e}", exc_info=True)
        # Fallback: Return the first Pokemon from the vector search
        first_match = top_pokemon_list[0]
        return {
            'name': first_match['name'],
            'explanation': f"Based on similarity, {first_match['name']} seems like a good starting point (LLM refinement failed)."
        }

@app.after_request
def after_request(response):
    if response.status_code >= 500:
        log_level = logging.ERROR  # Log 5xx as ERROR
    elif response.status_code >= 400:
        log_level = logging.WARNING  # Log 4xx as WARNING
    else:
        log_level = logging.DEBUG  # Log 2xx and 3xx as INFO

    logger.log(log_level, '%s %s %s %s',
                    request.remote_addr,
                    request.method,
                    request.path,
                    response.status_code)

    return response

@app.route('/', methods=['GET', 'POST'])
def recommend():
    final_pokemon_recommendation = None
    error_msg = None

    if request.method == 'POST':
        query_text = request.form.get('query_text')
        logger.info(f"Received query: {query_text}")

        if not query_text:
             error_msg = "Please describe the Pokemon you're looking for."
        else:
            conn = get_db_connection()
            if not conn:
                error_msg = "Database connection failed."
                # Use render_template now
                return render_template('index.html', error=error_msg), 500

            try:
                cursor = conn.cursor()
                query_embedding = generate_embedding_app(query_text) # Use chosen function

                if query_embedding:
                    query_sql = """
                        SELECT name, description
                        FROM pokemon
                        ORDER BY embedding <=> %s -- Cosine distance
                        LIMIT 3;
                    """
                    cursor.execute(query_sql, (str(query_embedding),))
                    results = cursor.fetchall()
                    logger.info(f"Found {len(results)} candidates from vector search.")
                else:
                    error_msg = "Failed to process your query (embedding generation failed)."
                    logger.warning("Could not generate query embedding.")
                    result = None

                if results:
                    top_3_candidates = [{'name': row[0], 'description': row[1]} for row in results]

                    # --- Call LLM to refine ---
                    llm_choice = call_llm_to_choose_genai(query_text, top_3_candidates)

                else: # No results from vector search
                    error_msg = "Could not find any potentially matching Pokemon."
                    logger.info("No matches found from vector search.")

                # --- Prepare final result based on LLM choice ---
                if llm_choice and llm_choice.get('name'):
                    chosen_name = llm_choice['name']
                    # Find the description for the chosen Pokemon from our top 3 list
                    chosen_description = next((p['description'] for p in top_3_candidates if p['name'] == chosen_name), "No description found.")

                    logger.info(f"LLM recommended: {chosen_name}")
                    signed_image_url = get_signed_url(chosen_name)
                    final_pokemon_recommendation = {
                        "name": chosen_name,
                        "description": chosen_description, # Pass the actual description
                        "image_url": signed_image_url,
                        "explanation": llm_choice.get('explanation', '') # Add explanation
                    }
                elif top_3_candidates and not llm_choice: # LLM failed, but had candidates
                     # Fallback: Use the #1 vector search result if LLM fails
                     first_match = top_3_candidates[0]
                     logger.warning("LLM choice failed or was invalid, using top vector search result.")
                     signed_image_url = get_signed_url(first_match['name'])
                     final_pokemon_recommendation = {
                        "name": first_match['name'],
                        "description": first_match['description'],
                        "image_url": signed_image_url,
                        "explanation": "This Pokémon had the closest description match based on our search." # Generic explanation
                    }
                # If embedding failed or no candidates found, error_msg is already set

                
                cursor.close()
                conn.close()

            except psycopg2.Error as db_err:
                logger.error(f"Database error: {db_err}")
                error_msg = "A database error occurred."
                if conn: conn.rollback()
            except Exception as e:
                logger.error(f"Error during query or processing: {e}", exc_info=True)
                error_msg = "An application error occurred."
                if conn: conn.rollback()
            finally:
                if conn: conn.close()

    # Use render_template for both GET and POST responses
    return render_template('index.html', pokemon=final_pokemon_recommendation, error=error_msg)


if __name__ == '__main__':
    # Set debug=False for production/deployment
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))