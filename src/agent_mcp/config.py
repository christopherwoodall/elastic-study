import os

from elasticsearch import AsyncElasticsearch

# Load environment variables
ES_URL = os.environ.get("ELASTIC_URL", "http://localhost:9200")

# Initialize globally accessible async client
es_client = AsyncElasticsearch(hosts=[ES_URL])
