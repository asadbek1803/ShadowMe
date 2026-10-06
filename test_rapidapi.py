import requests

url = "https://www.youtube.com/watch?v=aW36iZ_BFS4"
api_url = "https://youtube-info-download-api.p.rapidapi.com/ajax/download.php"
querystring = {"format": "360", "add_info": "1", "url": url}
headers = {
    "x-rapidapi-key": "022e4eb3f2msha1f7931fb9addfcp113296jsn597d9f47e3d2",
    "x-rapidapi-host": "youtube-info-download-api.p.rapidapi.com",
    "Content-Type": "application/json"
}

response = requests.get(api_url, headers=headers, params=querystring)
data = response.json()
print('Init data keys:', data.keys())
print('title:', data.get('title'))
print('thumbnail:', data.get('thumbnail'))
