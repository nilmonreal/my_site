from django.shortcuts import render
from django.core.cache import cache
import feedparser
import re
import html
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

# --- HELPER FUNCTIONS ---

def get_real_url(google_url):
    try:
        parsed = urlparse(google_url)
        real_url = parse_qs(parsed.query).get('url', [None])[0]
        return real_url if real_url else google_url
    except:
        return google_url

def clean_text(text):
    """
    Cleans up the text:
    1. Removes HTML tags.
    2. Fixes &quot; -> "
    3. Removes extra spaces.
    """
    if not text: return ""
    # Remove HTML tags
    text = re.sub('<[^<]+?>', '', text)
    # Fix entities (&quot;, &nbsp;, etc)
    text = html.unescape(text)
    # Remove multiple spaces/newlines
    text = " ".join(text.split())
    return text

def scrape_article_data(url):
    """
    Visits the URL and returns a DICTIONARY with both Image and Description.
    """
    data = {"image": None, "description": None}
    
    if not url: return data
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=2)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 1. FIND IMAGE
            og_image = soup.find("meta", property="og:image")
            if og_image:
                data["image"] = og_image.get("content")
            
            # 2. FIND DESCRIPTION (The official summary)
            # We try 'og:description' first, then standard 'description'
            og_desc = soup.find("meta", property="og:description")
            if og_desc:
                data["description"] = clean_text(og_desc.get("content"))
            else:
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc:
                    data["description"] = clean_text(meta_desc.get("content"))
                    
    except:
        pass # If it fails, we return the empty data dict
        
    return data

def parse_date(date_string):
    try:
        dt = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%d %b %Y") 
    except:
        return date_string

def smart_truncate(content, length=160, suffix='...'):
    """
    Cuts the text but ensures we don't cut a word in half.
    """
    if len(content) <= length:
        return content
    else:
        # Cut to limit
        content = content[:length]
        # If the last char is not a space, cut back to the previous space
        if content[-1] != " ":
            content = content.rsplit(' ', 1)[0]
        return content + suffix

# --- THE WORKER FUNCTION ---

def process_single_post(entry):
    # 1. Basic cleaning
    clean_title = clean_text(entry.title)
    real_link = get_real_url(entry.link)
    
    # 2. Scrape REAL data (Image + Summary)
    scraped_data = scrape_article_data(real_link)
    
    # 3. Determine Final Description
    # If we found a real description on the site, use it.
    # If not, fallback to the Google RSS snippet (cleaned).
    if scraped_data["description"]:
        final_excerpt = smart_truncate(scraped_data["description"])
    else:
        # Fallback to Google's messy snippet, but cleaned
        rss_snippet = clean_text(entry.content[0].value)
        final_excerpt = smart_truncate(rss_snippet)

    # 4. Fallback Image
    final_image = scraped_data["image"]
    if not final_image:
        final_image = "https://placehold.co/600x400/E30613/FFFFFF?text=PSOE+News"

    return {
        "title": clean_title,
        "date": parse_date(entry.published),
        "excerpt": final_excerpt, # Now using the high-quality description
        "link": real_link,
        "image": final_image
    }

def get_cached_news():
    cached_data = cache.get('psoe_news')
    if cached_data:
        return cached_data

    print("Cache miss: Fetching feed and scraping concurrently...")
    rss_url = "https://www.google.com/alerts/feeds/16780431236428968089/13199558778761765910"
    feed = feedparser.parse(rss_url)

    if feed.status != 200:
        return []

    posts = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(process_single_post, feed.entries)
        posts = list(results)
    
    cache.set('psoe_news', posts, 900)
    
    return posts

# --- VIEW FUNCTIONS ---

def index(request):
    all_posts = get_cached_news()
    recent_posts = all_posts[:6] 
    context = { "posts": recent_posts }
    return render(request, 'blog/index.html', context)

def posts(request):
    all_posts = get_cached_news()
    context = { "posts": all_posts }
    return render(request, 'blog/posts.html', context)