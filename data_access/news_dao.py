from config.database import db

class NewsDAO:
    def __init__(self):
        self.collection = db['news']

    def insert(self, url: str) -> bool:
        self.collection.insert_one({'url': url})
        return True

    def exists(self, url: str) -> bool:
        return self.collection.count_documents({"url": url}, limit=1) > 0
    
    @staticmethod
    def normalize_url(domain, url):
        url = url.strip()
            
        if not url.startswith('http'):
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                url = f"{domain}{url}"
            else:
                url = f"{domain}/{url}"
        return url