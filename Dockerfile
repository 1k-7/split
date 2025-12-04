# Use a lightweight Python image to save VPS space
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install the required library
# We turn off cache to save space in the final image layer
RUN pip install --no-cache-dir pyTelegramBotAPI

# Copy your python script into the container
COPY bot.py .

# Create a volume for temporary file processing (optional but good for I/O)
VOLUME /app/temp

# Run the bot
CMD ["python", "bot.py"]
