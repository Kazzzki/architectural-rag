import translator

def summarize_news(news_items, skip_translation=False):
    """
    Takes a list of news items and formats them into an HTML summary.
    Translates content to Japanese unless skip_translation is True.
    
    Args:
        news_items (list): List of dicts specific to the fetcher output.
        skip_translation (bool): If True, assumes items are already translated.
        
    Returns:
        str: HTML formatted string.
    """
    if not news_items:
        return "<p>過去24時間以内に新しいAIニュースは見つかりませんでした。</p>"
        
    html_content = "<h2>毎日のAIニュースダイジェスト</h2>"
    html_content += f"<p>過去24時間の記事が {len(news_items)} 件見つかりました。</p><hr>"
    
    # Sort by date descending
    news_items.sort(key=lambda x: x['published'], reverse=True)
    
    # Limit number of articles if we are translating, to avoid heavy load
    # If already translated (skip_translation=True), we might still want to limit or just take all.
    # Let's keep the limit for email readability regardless.
    max_articles = 20
    if len(news_items) > max_articles:
        html_content += f"<p>※記事が多すぎるため、最新の{max_articles}件のみを表示しています。</p>"
        news_items = news_items[:max_articles]

    if not skip_translation:
        print("Translating articles... (this may take a while)")
    
    for i, item in enumerate(news_items):
        if not skip_translation:
            print(f"Translating {i+1}/{len(news_items)}: {item['title'][:30]}...")
            ja_title = translator.translate_text(item['title'])
            ja_summary = translator.translate_text(item['summary'])
        else:
            # Assume keys are already translated or we use them as is
            ja_title = item['title']
            ja_summary = item['summary']
        
        html_content += f"""
        <div style="margin-bottom: 20px;">
            <h3 style="margin-bottom: 5px;"><a href="{item['link']}">{ja_title}</a></h3>
            <p style="font-size: 0.9em; color: #555; margin-top: 0;">
                {item['source']} - {item['published']}
            </p>
            <p>{ja_summary}</p>
        </div>
        """
        
    html_content += "<hr><p><em>Python AIニュースボットによって作成されました</em></p>"
    
    return html_content
