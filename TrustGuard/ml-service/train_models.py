import os
# pyrefly: ignore [missing-import]
import joblib
# pyrefly: ignore [missing-import]
import numpy as np
# pyrefly: ignore [missing-import]
import pandas as pd
# pyrefly: ignore [missing-import]
from sklearn.feature_extraction.text import TfidfVectorizer
# pyrefly: ignore [missing-import]
from sklearn.linear_model import LogisticRegression
# pyrefly: ignore [missing-import]
from sklearn.naive_bayes import MultinomialNB
# pyrefly: ignore [missing-import]
from sklearn.ensemble import RandomForestClassifier

# Ensure models directory exists
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

def train_news_model():
    print("Training News Model...")
    # Synthetic/representative dataset for real vs fake news
    data = {
        'text': [
            # Real News
            "The international trade summit concluded today with a historic agreement on climate policy and carbon emission caps.",
            "Local authorities announced a new public transit expansion project aimed at reducing traffic congestion in the downtown area.",
            "Scientists at the university have developed a highly efficient solar panel that functions even under cloudy conditions.",
            "The central bank adjusted interest rates by a quarter percentage point to stabilize inflation and support economic growth.",
            "A new study published in the journal indicates that regular physical activity increases life expectancy in adults.",
            "The regional health department is launching a free vaccination drive for flu season starting next Monday.",
            "City council members voted unanimously to increase funding for public library renovations and community programs.",
            "Stock indices finished higher today after a strong earnings report from several major tech and retail companies.",
            "Heavy rainfall has caused moderate flooding in low-lying agricultural sectors, leading to temporary road closures.",
            "Astronomers have observed a distant planet that could support liquid water, using the latest space telescope data.",
            
            # Fake News
            "SHOCKING! Scientists discover lizard people are secretly living beneath the city and controlling the local government!",
            "This miracle cure is being hidden by big pharma because it completely cures all diseases in less than 24 hours!",
            "Conspiracy exposed: 5G waves are being used to control minds and transmit secret government propaganda directly.",
            "Unbelievable scam! This hidden loophole lets you double your bank account overnight with zero risk or effort.",
            "BREAKING: Secret documents prove that aliens have landed in a hidden facility and are negotiating with world leaders.",
            "The truth big pharma won't tell you: standard food items are poisoned to keep the population sick.",
            "Miracle water source found in the desert cures all medical ailments instantly, government tries to shut it down.",
            "A shocking secret report reveals the election was entirely simulated by an advanced supercomputer simulation.",
            "Propaganda warning: mainstream media is hiding the fact that 5G waves are causing mass bird migrations.",
            "Billionaire reveals unbelievable conspiracy to replace all currency with digital microchips by next month."
        ],
        'label': [
            'Real', 'Real', 'Real', 'Real', 'Real', 'Real', 'Real', 'Real', 'Real', 'Real',
            'Fake', 'Fake', 'Fake', 'Fake', 'Fake', 'Fake', 'Fake', 'Fake', 'Fake', 'Fake'
        ]
    }
    
    df = pd.DataFrame(data)
    
    # Vectorization
    vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
    X = vectorizer.fit_transform(df['text'])
    y = df['label']
    
    # Train Logistic Regression Model
    model = LogisticRegression(C=1.0, random_state=42)
    model.fit(X, y)
    
    # Save Vectorizer and Model
    joblib.dump(vectorizer, os.path.join(MODELS_DIR, "news_vectorizer.joblib"))
    joblib.dump(model, os.path.join(MODELS_DIR, "news_model.joblib"))
    print("News Model and Vectorizer saved successfully.")

def train_review_model():
    print("Training Review Model...")
    # Synthetic/representative dataset for genuine vs fake reviews
    data = {
        'text': [
            # Genuine Reviews
            "I bought this vacuum cleaner last week and it has excellent suction power. The battery life is decent, lasting around 30 minutes.",
            "The keyboard feels comfortable to type on, but some keys are a bit noisy. Delivery was fast and packaging was secure.",
            "This book provides a great introduction to database design. The examples are clear, though some chapters feel repetitive.",
            "The jacket is warm and fits true to size, but the zipper feels a little cheap. Overall, decent value for the price.",
            "Sound quality is good for the price, but the earbuds tend to slip out during heavy running or workouts.",
            "Excellent build quality and sleek design. The screen is bright, but battery performance could be better under heavy load.",
            "The instructions were slightly confusing, but once assembled, the desk is sturdy and offers plenty of storage space.",
            "It works as advertised, but the software application can be laggy at times on older phone models.",
            
            # Fake/Spam Reviews
            "BUY THIS NOW! This is the best product ever! It changed my life completely! Click here for a free gift and discount!",
            "Make money fast! Get this amazing item and receive guaranteed success within 3 days. Free gift included!",
            "AMAZING AMAZING AMAZING! Best product ever purchased, completely perfect with absolutely zero issues!",
            "Earn cash easily by buying this item. Click here to claim your free reward and start earning today!",
            "Unbelievable results! This product changed my life overnight. Buy this now before stock runs out!",
            "This is a total scam. Go to this website to get the real deal and save 90% off retail prices now!",
            "Click here for a special deal! Buy this product now to get a free lifetime warranty and cash prize!",
            "Amazing quality, guaranteed satisfaction! Click this link to get yours for free today!"
        ],
        'label': [
            'Genuine', 'Genuine', 'Genuine', 'Genuine', 'Genuine', 'Genuine', 'Genuine', 'Genuine',
            'Fake', 'Fake', 'Fake', 'Fake', 'Fake', 'Fake', 'Fake', 'Fake'
        ]
    }
    
    df = pd.DataFrame(data)
    
    # Vectorization
    vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
    X = vectorizer.fit_transform(df['text'])
    y = df['label']
    
    # Train Multinomial Naive Bayes Model
    model = MultinomialNB()
    model.fit(X, y)
    
    # Save Vectorizer and Model
    joblib.dump(vectorizer, os.path.join(MODELS_DIR, "review_vectorizer.joblib"))
    joblib.dump(model, os.path.join(MODELS_DIR, "review_model.joblib"))
    print("Review Model and Vectorizer saved successfully.")

def extract_url_features(url):
    lower_url = url.lower()
    
    # 1. SSL Protocol check
    ssl_valid = 1 if lower_url.startswith('https://') else 0
    
    # 2. Suspicious keywords presence
    suspicious_keywords = ['login', 'signin', 'verify', 'update-account', 'secure-bank', 'paypal', 'netflix-secure', 'wallet', 'crypto']
    suspicious_keyword = 1 if any(kw in lower_url for kw in suspicious_keywords) else 0
    
    # 3. Special character count ratio
    special_chars = set(['-', '.', '?', '=', '&', '@', '_'])
    special_char_count = sum(1 for char in url if char in special_chars)
    
    # 4. Shady TLD match
    shady_tlds = ['.xyz', '.info', '.top', '.click', '.date', '.win', '.party', '.cc']
    shady_tld = 1 if any(tld in lower_url for tld in shady_tlds) else 0
    
    # 5. Length of URL
    url_length = len(url)
    
    return [ssl_valid, suspicious_keyword, special_char_count, shady_tld, url_length]

def train_phishing_model():
    print("Training Phishing Model...")
    # List of Safe (0) and Phishing (1) URLs
    urls = [
        # Safe URLs (Label: 0)
        ("https://www.google.com", 0),
        ("https://www.github.com/Ayush1015/Trust-Guard", 0),
        ("https://www.wikipedia.org/wiki/Main_Page", 0),
        ("https://www.amazon.com/gp/goldbox", 0),
        ("https://www.nytimes.com/section/world", 0),
        ("https://www.microsoft.com/en-us/store", 0),
        ("https://www.linkedin.com/feed/", 0),
        ("https://www.netflix.com/browse", 0),
        ("https://www.paypal.com/signin", 0),
        ("https://www.cnn.com/world", 0),
        
        # Phishing URLs (Label: 1)
        ("http://verify-paypal-account-security.xyz/login", 1),
        ("http://secure-bank-update.info/login.php?user=test", 1),
        ("http://netflix-secure-update.top/login", 1),
        ("http://wallet-crypto-connect.click/index.html", 1),
        ("http://signin-google-account-verify.win/auth", 1),
        ("https://secure-bank-login-page-verification-update.cc/verify", 1),
        ("http://claim-free-btc-reward.party/spin", 1),
        ("http://update-microsoft-office-security.date/login", 1),
        ("http://verify-your-identity-paypal.xyz/auth", 1),
        ("http://free-giftcard-deals.click/redeem", 1)
    ]
    
    X = []
    y = []
    for url, label in urls:
        features = extract_url_features(url)
        X.append(features)
        y.append(label)
        
    X = np.array(X)
    y = np.array(y)
    
    # Train Random Forest Classifier
    model = RandomForestClassifier(n_estimators=50, random_state=42)
    model.fit(X, y)
    
    # Save Model
    joblib.dump(model, os.path.join(MODELS_DIR, "phishing_model.joblib"))
    print("Phishing Model saved successfully.")

if __name__ == "__main__":
    train_news_model()
    train_review_model()
    train_phishing_model()
    print("All models trained and saved to:", MODELS_DIR)
