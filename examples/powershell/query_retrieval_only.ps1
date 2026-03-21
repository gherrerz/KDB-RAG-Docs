$baseUrl = 'http://127.0.0.1:8000'

$body = @{
    repo_id = 'mall'
    query = 'donde esta la configuracion de neo4j'
    top_n = 60
    top_k = 15
    include_context = $false
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$baseUrl/query/retrieval" -ContentType 'application/json' -Body $body
