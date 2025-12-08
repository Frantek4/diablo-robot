from tinydb import TinyDB, Query

class NewsDAO:
    def __init__(self):
        self.table = TinyDB('database.json').table('news')

    def insert(self, url: str) -> bool:
        self.table.insert({'url': url})
        return True

    def exists(self, url: str) -> bool:
        query = Query()
        result = self.table.search(query.url == url)
        return len(result) > 0
    
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