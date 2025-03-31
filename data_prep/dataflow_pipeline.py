import apache_beam as beam
from apache_beam.io import fileio
from beam_postgres.io import WriteToPostgres
from apache_beam.options.pipeline_options import PipelineOptions
import argparse
import logging
import os
from google import genai
from google.genai.types import EmbedContentConfig
import re
import time  # Import the time module

# Define the embedding dimension
EMBEDDING_DIM = 768
MODEL_NAME = "text-embedding-005"


def log_matched_file(match_result):
    """Logs the metadata of a matched file."""
    logging.info(f"Matched file: {match_result}")
    return match_result


def log_read_file(readable_file):
    """Logs the path of a file being read."""
    logging.info(f"Reading file: {readable_file}")
    return readable_file


def generate_embedding_genai(text):
    """Generates text embedding using Google GenAI SDK."""
    if not text:
        logging.warning("Received empty text for embedding.")
        return None

    try:
        # ADC should be picked up automatically by the client on Dataflow workers
        PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
        region = "us-central1"
        client = genai.Client(
            vertexai=True, project=PROJECT_ID, location=region
        )  # Create client on demand

        logging.debug(f"Sending text to GenAI embed_content: {text[:60]}...")
        start_time = time.time()  # Record the start time
        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=[
                text,
            ],
            config=EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",  # Optional
                output_dimensionality=768,  # Optional
            ),
        )
        end_time = time.time()  # Record the end time
        logging.debug(
            f"Received response from GenAI embed_content in {end_time - start_time:.2f} seconds."
        )

        # Response structure is {'embedding': [float, float, ...]}
        embedding_vector = response.embeddings  # Use .get for safer access

        if embedding_vector and isinstance(embedding_vector, list):
            # logging.info(f"Generated embedding dim {len(embedding_vector)} for text: {text[:50]}...")
            if len(embedding_vector) != EMBEDDING_DIM:
                logging.warning(
                    f"Expected embedding dim {EMBEDDING_DIM} but got {len(embedding_vector)}."
                )
            return embedding_vector  # Return the list of floats
        else:
            logging.warning(
                f"GenAI SDK returned no valid embedding structure for text: {text[:50]}..."
            )
            logging.warning(
                f"GenAI Raw Response: {response}"
            )  # Log raw response for debugging
            return None

    except Exception as e:
        logging.error(
            f"Failed to get embedding from GenAI SDK for text '{text[:50]}...': {e}",
            exc_info=True,
        )
        # Log details about the exception if possible
        if hasattr(e, "response"):
            logging.error(f"GenAI API Error Response: {e.response}")
        return None


# --- Keep extract_name_from_filename as before ---
def extract_name_from_filename(filename):
    try:
        base = os.path.basename(filename)
        name, _ = os.path.splitext(base)
        return name.capitalize()
    except Exception as e:
        logging.warning(
            f"Could not extract name from filename '{filename}'. Error: {e}"
        )
        return None


class ProcessFileDoFn(beam.DoFn):
    """A DoFn to process files using the GenAI SDK."""

    def process(self, readable_file):
        """Reads file content, extracts name, generates embedding."""
        filename = readable_file.metadata.path
        logging.info(f"Processing file: {filename}")
        name = extract_name_from_filename(filename)
        if not name:
            yield beam.pvalue.TaggedOutput(
                "failed", f"Name extraction failed for {filename}"
            )
            return

        try:
            content = readable_file.read().decode("utf-8").strip()
            if not content:
                logging.warning(f"File {filename} is empty.")
                yield beam.pvalue.TaggedOutput(
                    "failed", f"Empty content for {filename}"
                )
                return

            # Generate embedding using the GenAI SDK function
            embedding_response = generate_embedding_genai(content)  # Get embedding response

            if embedding_response is None or not hasattr(embedding_response[0], 'values'):
                logging.warning(
                    f"Skipping {name} due to embedding generation failure."
                )
                yield beam.pvalue.TaggedOutput(
                    "failed", f"Embedding failed for {filename}"
                )
                return

            embedding = embedding_response[0].values # Access the values attribute

            logging.info(f"Successfully processed: {name}")

            # Format the embedding as a string for PostgreSQL vector type
            #embedding_str = '[' + ','.join(f'{x:.10f}' for x in embedding) + ']'
            #logging.info(f"Formatted embedding: {embedding_str[:100]}...")

            yield {  # Yield the successful record directly
                "name": name,
                "description": content,
                "embedding": embedding,
            }
        except Exception as e:
            logging.error(f"Error processing file {filename}: {e}", exc_info=True)
            yield beam.pvalue.TaggedOutput(
                "failed", f"General error processing {filename}: {e}"
            )


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_pattern",
        dest="input_pattern",
        required=True,
        help="Input file pattern (GCS path like gs://bucket/folder/*.txt)",
    )
    parser.add_argument(
        "--db_host", dest="db_host", required=True, help="Cloud SQL Private IP"
    )
    parser.add_argument(
        "--db_name", dest="db_name", required=True, help="Database name"
    )
    parser.add_argument(
        "--db_user", dest="db_user", required=True, help="Database user"
    )
    parser.add_argument(
        "--db_password",
        dest="db_password",
        required=True,
        help="Database password",
    )
    # REMOVED: --vertex_project and --vertex_region arguments

    known_args, pipeline_args = parser.parse_known_args(argv)
    pipeline_options = PipelineOptions(
        pipeline_args, save_main_session=True, streaming=False
    )

    # Extract bucket name from input pattern
    match = re.match(r"gs://([^/]+)/", known_args.input_pattern)
    if match:
        bucket_name = match.group(1)
        logging.info(f"Dataflow job will read from GCS bucket: {bucket_name}")
    else:
        logging.warning(
            f"Could not extract bucket name from input pattern: {known_args.input_pattern}"
        )

    with beam.Pipeline(options=pipeline_options) as pipeline:
        matched_files = (
            pipeline
            | "MatchFiles" >> fileio.MatchFiles(known_args.input_pattern)
            | "LogMatchedFiles" >> beam.Map(log_matched_file)
        )

        if not matched_files:
            logging.error(f"No files matched the input pattern: {known_args.input_pattern}")
            return  # Exit the pipeline early


        read_files = (
            matched_files
            | "ReadMatches" >> fileio.ReadMatches()
            | "LogReadFiles" >> beam.Map(log_read_file)
        )

        processed_records = (
            read_files
            | "ProcessFile"
            >> beam.ParDo(ProcessFileDoFn()).with_outputs(
                "failed", main="processed"
            )
        )

        # Write successful records to DB
        (
            processed_records["processed"]
            | "WriteToPostgres"
            >> WriteToPostgres(
                host=known_args.db_host,
                database=known_args.db_name,
                table="pokemon",
                user=known_args.db_user,
                password=known_args.db_password,
                port=5432,
            )
        )

        # Log failed records
        (
            processed_records["failed"]
            | "LogFailures"
            >> beam.Map(lambda x: logging.error(f"Failed record reason: {x}"))
        )


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    # Set google-generativeai log level higher if needed to reduce noise
    run()
