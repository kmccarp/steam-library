import csv
import os
import time

import requests
from datetime import datetime
from tqdm import tqdm

# Replace with your Steam API key and Steam ID or add them as env vars
# get API key from https://steamcommunity.com/dev/apikey
# get Steam id from https://store.steampowered.com/account/

# use env var STEAM_API_KEY
STEAM_API_KEY = os.getenv('STEAM_API_KEY')
STEAM_ID = os.getenv('STEAM_ID')

MIN_WAIT_SECONDS = 1
MAX_WAIT_SECONDS = 60
MAX_ATTEMPTS = 10

response_cache = {}

def request(url, ignore_error=False, wait_seconds=0, attempts=0):
    if url in response_cache:
        return response_cache[url]
    try:
        # wait for wait_seconds
        if wait_seconds > 0:
            print(f"Waiting for {str(wait_seconds)} second(s) before calling {url}")
            time.sleep(wait_seconds)
        response = requests.get(url)
        response.raise_for_status()
        response_cache[url] = response
        return response
    except requests.RequestException as e:
        if e.response is not None and e.response.status_code == 429:
            # exponential backoff up to max time and max attempts
            if attempts + 1 > MAX_ATTEMPTS:
                print(f"Reached max attempts for {url}. Exiting.")
                return
            wait_time_seconds = min(wait_seconds * 2, MAX_WAIT_SECONDS) if wait_seconds > 0 else MIN_WAIT_SECONDS
            print(f"Got 429 when calling {url}, trying again after {str(wait_time_seconds)} second(s).")
            return request(url, ignore_error, wait_time_seconds, attempts + 1)
        if not ignore_error:
            print(f"Exception occurred while fetching data from {url}:", e)
            print("Response content:", e.response.content if e.response is not None else 'No response')
        raise e

# Helper function to format dates
def format_date(date_str):
    try:
        # Parse date from any common format and convert to ISO format (YYYY-MM-DD)
        dt = datetime.strptime(date_str, "%d %b, %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return 'Unknown Release Date'

# Get owned games
def get_owned_games(steam_id, api_key):
    url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={api_key}&steamid={steam_id}&include_appinfo=true&include_played_free_games=true&format=json"
    response = request(url)
    data = response.json()
    return data['response']['games']

# Fetch global achievement percentages to determine if game is beaten
def is_game_beaten(appid, steam_id, api_key):
    # Fetch game achievements for the player
    url = f"https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/?appid={appid}&key={api_key}&steamid={steam_id}"
    try:
        response = request(url, True)
    except requests.RequestException as e:
        return False
    data = response.json()
    # Heuristic: Check if 50% of achievements have been unlocked
    if 'playerstats' in data and 'achievements' in data['playerstats']:
        achievements = data['playerstats']['achievements']
        total_achievements = len(achievements)
        unlocked_achievements = sum(ach['achieved'] for ach in achievements)
        return unlocked_achievements >= total_achievements / 2
    return False

# Fetch review summary
def get_review_summary(appid):
    url = f"https://store.steampowered.com/appreviews/{appid}?json=1&num_per_page=1"
    try:
        response = request(url, True)
    except requests.RequestException as e:
        return 'Error Fetching Reviews'
    data = response.json()
    if 'query_summary' in data:
        return data['query_summary']['review_score_desc']
    return 'No Reviews'

# Fetch Metacritic score
def get_metacritic_score(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
    try:
        response = request(url, True)
    except requests.RequestException as e:
        return 'Error Fetching Metacritic Score'
    data = response.json()
    if str(appid) in data and 'metacritic' in data[str(appid)]['data']:
        return data[str(appid)]['data']['metacritic']['score']
    return 'No Score'

# Fetch release date
def get_release_date(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
    try:
        response = request(url, True)
    except requests.RequestException as e:
        return 'Error Fetching Release Date'
    data = response.json()
    if str(appid) in data and 'release_date' in data[str(appid)]['data']:
        return format_date(data[str(appid)]['data']['release_date']['date'])
    return 'Unknown Release Date'

def main():
    steam_id = STEAM_ID
    if not steam_id:
        print("Could not retrieve Steam ID. Exiting.")
        return

    owned_games = get_owned_games(steam_id, STEAM_API_KEY)
    if not owned_games:
        print("Could not retrieve owned games or no games found.")
        return

    # Create CSV and write header
    with open('steam_library.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Name', 'Review Rating', 'Metacritic Score', 'Playtime in Minutes', 'Date Released',
                      'Last Played/Added', 'Beaten']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        # Fetch game details
        for game in tqdm(owned_games, desc="Processing games"):
            appid = game['appid']
            name = game['name']
            playtime_minutes = game.get('playtime_forever', 0)
            last_played_timestamp = game.get('rtime_last_played', 0)
            last_played_date = datetime.utcfromtimestamp(last_played_timestamp).strftime(
                '%Y-%m-%d') if last_played_timestamp else 'Never Played'
            try:
                review_rating = get_review_summary(appid)
                metacritic_score = get_metacritic_score(appid)
                release_date = get_release_date(appid)
                beaten = is_game_beaten(appid, steam_id, STEAM_API_KEY)
                # Write row
                writer.writerow({
                    'Name': name,
                    'Review Rating': review_rating,
                    'Metacritic Score': metacritic_score,
                    'Playtime in Minutes': playtime_minutes,
                    'Date Released': release_date,
                    'Last Played/Added': last_played_date,
                    'Beaten': beaten
                })
            except Exception as e:
                print(f"Exception occurred while processing game {appid} ({name}):", e)
                continue

if __name__ == "__main__":
    main()
