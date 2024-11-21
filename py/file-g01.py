import json
from datetime import datetime, timedelta
import pandas as pd
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import re
import time

# 作業日（実行日）の前日を設定
TARGET_DATE = datetime.now() - timedelta(days=1)

# スクレイピング対象グループを限定
TARGET_GROUPS = ['g01']  # 必要に応じてグループを追加

# HTML構造の定義
EXPECTED_CLASSES = {
    "news_link": "cDTGMJ",          # ニュースリンクのクラス
    "content_div": "iiJVBF",        # コンテンツ全体を含むdivのクラス
    "title_div": "dHAJpi",          # タイトルを含むdivのクラス
    "time": "faCsgc",               # 時間表示のクラス
    "article_body": "article_body"   # 記事本文のクラス
}

def create_save_directory(target_date):
    """保存ディレクトリを作成する"""
    save_dir = Path(target_date.strftime('%Y-%m%d'))  # フォーマット例: 2024-1120
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir

def save_articles_to_csv(article_data, media_en, target_date):
    """記事データをCSVに保存する"""
    if not article_data:
        return

    save_dir = create_save_directory(target_date)
    filename = f"{target_date.strftime('%Y%m%d')}-{media_en}.csv"
    file_path = save_dir / filename

    columns = [
        "headline",
        "mainEntityOfPage",
        "image",
        "datePublished",
        "dateModified",
        "author",
        "media_en",
        "media_jp",
        "str_count",
        "body",
        "images",
        "external_links"
    ]

    df = pd.DataFrame(article_data)
    df = df[columns]
    df.to_csv(file_path, index=False, encoding="utf-8")
    print(f"Articles saved as {file_path}")

def fetch_full_article(url, timeout_duration=30):
    """記事の本文を取得する"""
    full_text = ''
    json_ld_data = None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout_duration)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        script_tag = soup.find('script', type='application/ld+json')
        if script_tag:
            try:
                json_ld_data = json.loads(script_tag.string)
                if not isinstance(json_ld_data, dict):
                    json_ld_data = {}
            except json.JSONDecodeError:
                json_ld_data = {}

        article_body = soup.find('div', {'class': EXPECTED_CLASSES["article_body"]})
        if article_body:
            full_text = article_body.get_text('\n', strip=True)

        return re.sub(r'\s+', ' ', full_text).strip(), json_ld_data
    except Exception as e:
        print(f"Error fetching article {url}: {e}")
        return None, None

def get_yahoo_news_urls(base_url, max_pages=10):
    """Yahooニュースから複数ページの記事リンクを取得する"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    timeout_duration = 30  # タイムアウト秒数として明示的に設定
    urls = []
    current_page = 1  # 最初のページから開始

    while current_page <= max_pages:  # 最大ページ数までループ
        try:
            # ページURLの生成
            current_url = f"{base_url}?page={current_page}" if current_page > 1 else base_url

            # ページのリクエスト
            response = requests.get(current_url, headers=headers, timeout=timeout_duration)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # 記事リンクの取得
            news_items = soup.find_all("a", class_=EXPECTED_CLASSES["news_link"])
            if not news_items:
                print(f"No links found on page {current_page} for base URL: {base_url}")
                break

            for item in news_items:
                url = item.get('href')
                if url and "yahoo.co.jp" in url:
                    urls.append(url)

            # スリープを追加（1.5～3秒のランダムな間隔）
            time.sleep(random.uniform(1.5, 3))

            print(f"Page {current_page}: Found {len(news_items)} links")
            current_page += 1

        except Exception as e:
            print(f"Error fetching news URLs on page {current_page} from {base_url}: {e}")
            break

    print(f"Total {len(urls)} URLs found for base URL: {base_url}")
    return urls



def process_group(group, urls_df, target_date):
    """グループごとの処理を行う"""
    print(f"Processing group: {group}")
    group_data = urls_df[urls_df['group'] == group]

    if group_data.empty:
        print(f"No URLs found for group {group}")
        return

    for _, row in group_data.iterrows():
        media_en = row['media_en']
        media_jp = row['media_jp']
        base_url = row['url']

        # ページループを含む関数を呼び出し
        article_links = get_yahoo_news_urls(base_url, max_pages=10)  # max_pages を明示的に整数で指定
        article_data = []

        for link in article_links:
            article_text, json_ld_data = fetch_full_article(link)
            if article_text and json_ld_data:
                article_data.append({
                    "headline": json_ld_data.get("headline", ""),
                    "mainEntityOfPage": json_ld_data.get("mainEntityOfPage", {}).get("@id", ""),
                    "image": json_ld_data.get("image", ""),
                    "datePublished": json_ld_data.get("datePublished", ""),
                    "dateModified": json_ld_data.get("dateModified", ""),
                    "author": json_ld_data.get("author", {}).get("name", ""),
                    "media_en": media_en,
                    "media_jp": media_jp,
                    "str_count": len(article_text),
                    "body": article_text,
                    "images": [],
                    "external_links": []
                })

        save_articles_to_csv(article_data, media_en, target_date)

def main():
    """メインの処理"""
    print(f"Starting scraping for date: {TARGET_DATE.strftime('%Y-%m-%d')}")

    csv_file_path = 'url/url_group.csv'  # リポジトリ内の相対パス
    urls_df = pd.read_csv(csv_file_path)

    for group in TARGET_GROUPS:
        process_group(group, urls_df, TARGET_DATE)

    print("\nAll processing completed!")

if __name__ == "__main__":
    main()
