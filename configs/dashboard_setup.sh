#!/bin/bash

# 1. Wait for Elasticsearch to be healthy
echo "Waiting for Elasticsearch..."
until curl -s http://elasticsearch:9200/_cluster/health | grep -q '\"status\":\"green\"\|\"status\":\"yellow\"'; do
  sleep 5
done

# 2. Create Index Template (Applies your mapping to all llm-proxy-logs* indices)
echo "Applying Index Mapping..."
curl -X PUT "http://elasticsearch:9200/_index_template/llm_proxy_template" -H 'Content-Type: application/json' -d'
{
  "index_patterns": ["llm-proxy-logs*"],
  "template": {
    "mappings": {
      "properties": {
        "request_id":         { "type": "keyword" },
        "timestamp":          { "type": "date" },
        "method":             { "type": "keyword" },
        "path":               { "type": "keyword" },
        "status_code":        { "type": "short" },
        "hostname":           { "type": "keyword" },
        "environment":        { "type": "keyword" },
        "client_ip":          { "type": "ip" },
        "user_agent":         { "type": "keyword" },
        "duration_ms":        { "type": "float" },
        "latest_user_prompt": { "type": "text" },
        "request_body":       { "type": "object", "dynamic": true },
        "response_body":      { "type": "object", "dynamic": true },
        "last_message":      { "type": "text" },
        "usage": {
        "properties": {
            "prompt_tokens": { "type": "integer" },
            "completion_tokens": { "type": "integer" },
            "total_tokens": { "type": "integer" }
        }
        }
      }
    }
  }
}'

# 3. Wait for Kibana to be healthy
echo "Waiting for Kibana..."
until curl -s -I http://kibana:5601/api/status | grep -q "HTTP/1.1 200 OK"; do
  sleep 5
done

# 4. Create Kibana Data View
echo "Creating Kibana Data View..."
curl -X POST "http://kibana:5601/api/data_views/data_view" \
  -H 'Content-Type: application/json' \
  -H 'kbn-xsrf: true' \
  -d'
{
  "data_view": {
     "title": "llm-proxy-logs*",
     "name": "LLM Proxy Logs"
  }
}'

5. Import Saved Dashboard
If you have an exported dashboard file (export.ndjson), uncomment below:
curl -X POST "http://kibana:5601/api/saved_objects/_import?overwrite=true" \
 -H "kbn-xsrf: true" \
 --form file=@/setup/dashboard.ndjson

# 6. Define a policy: Keep logs for 30 days, then delete
# echo "Creating Lifecycle Policy..."
# curl -X PUT "http://elasticsearch:9200/_ilm/policy/proxy_logs_policy" -H 'Content-Type: application/json' -d'
# {
#   "policy": {
#     "phases": {
#       "hot": { "actions": { "rollover": { "max_age": "1d", "max_size": "50gb" } } },
#       "delete": { "min_age": "30d", "actions": { "delete": {} } }
#     }
#   }
# }'
