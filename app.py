from flask import Flask, render_template, jsonify, request
import requests
import logging
from datetime import datetime
from flask_cors import CORS
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

logging.basicConfig(level=logging.DEBUG)
logger = app.logger

# Node details with tank dimensions added for volume calculation
NODES = [
    {
        "name": "Pump House 3",
        "coordinates": [17.4435, 78.3489],
        "channel_id": os.getenv("CHANNEL_ID_1"),
        "api_key": os.getenv("API_KEY_1"),
        "length": 4.90,  # Tank length in meters
        "breadth": 2.93,  # Tank breadth in meters
        "depth": 2.50,  # Tank depth in meters
    }
]

@app.route('/')
def home():
    """Render the homepage with map and node information."""
    return render_template('index.html', nodes=NODES)

@app.route('/api/data/<channel_id>')
def get_data(channel_id):
    """Fetch data from ThingSpeak for a specific channel."""
    api_key = request.args.get('api_key')
    if not api_key:
        return jsonify({"error": "API key is required"}), 400

    try:
        url = f'https://api.thingspeak.com/channels/{channel_id}/feeds.json'
        params = {
            'api_key': api_key,
            'results': 24  # Fetch last 24 entries for the graph
        }

        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        logger.debug(f"ThingSpeak Response: {data}")

        if 'feeds' not in data or not data['feeds']:
            return jsonify({"error": "No data available"}), 404

        # Find the node details for volume calculation
        node = next((n for n in NODES if n['channel_id'] == channel_id), None)
        if not node:
            return jsonify({"error": "Node configuration not found"}), 404

        length, breadth, depth = node['length'], node['breadth'], node['depth']

        processed_data = {
            'timestamps': [],
            'temperature': [],
            'distance': [],
            'volume': []  # Add volume calculation
        }

        for feed in reversed(data['feeds']):
            try:
                timestamp = datetime.strptime(feed['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                formatted_time = timestamp.strftime('%H:%M')

                temperature = None
                if 'field1' in feed and feed['field1'] is not None:
                    try:
                        temperature = round(float(feed['field1']), 1)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid temperature value: {feed['field1']}")

                distance = None
                volume = None
                if 'field2' in feed and feed['field2'] is not None:
                    try:
                        distance = round(float(feed['field2']), 1)  # Distance in cm
                        # Calculate volume based on distance
                        current_depth = depth - (distance / 100)  # Convert cm to meters
                        if current_depth > 0:
                            volume = round(length * breadth * current_depth, 2)
                        else:
                            volume = 0
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid distance value: {feed['field2']}")

                processed_data['timestamps'].append(formatted_time)
                processed_data['temperature'].append(temperature)
                processed_data['distance'].append(distance)
                processed_data['volume'].append(volume)

            except Exception as e:
                logger.error(f"Error processing feed entry: {e}")
                continue

        return jsonify(processed_data)

    except requests.RequestException as e:
        logger.error(f"Error fetching data from ThingSpeak: {e}")
        return jsonify({"error": "Failed to load data"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "An unexpected error occurred"}), 500


if __name__ == '__main__':
    app.run(debug=True)
