# Use official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Consider using --no-cache-dir for smaller images if needed later
RUN pip install -r requirements.txt

# --- NEW: Copy templates and static folders ---
COPY templates ./templates
COPY static ./static
# ---

# Copy the content of the local src directory to the working directory
COPY app.py .

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Define environment variable
ENV PORT 8080
# Ensure necessary ENV VARS for DB/AI are set in the deployment (e.g., GKE yaml)

# Run app.py when the container launches
CMD ["python", "app.py"]