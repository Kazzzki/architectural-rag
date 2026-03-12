from deep_translator import GoogleTranslator
import time

def translate_text(text, target_lang='ja'):
    """
    Translates text to target language using Google Translator.
    Truncates text if too long to avoid errors.
    """
    if not text:
        return ""
        
    try:
        # Simple truncation to avoid huge payloads (5000 chars is usually the limit)
        if len(text) > 4500:
            text = text[:4500] + "..."
            
        translator = GoogleTranslator(source='auto', target=target_lang)
        # Add small delay to be polite to the free API
        time.sleep(0.5)
        return translator.translate(text)
    except Exception as e:
        print(f"Translation failed: {e}")
        return text # Return original if translation fails
