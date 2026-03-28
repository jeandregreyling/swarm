import sys
sys.path.insert(0, '/home/seven/swarm')
from ddgs import DDGS

def search_web(query, max_results=3):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No results found."
        summary = ""
        for r in results:
            summary += f"Source: {r['href']}\n"
            summary += f"{r['title']}: {r['body']}\n\n"
        return summary.strip()
    except Exception as e:
        return f"[Search failed: {str(e)}]"

def verify_online(question, local_answer):
    results = search_web(question)
    return f"Web search results for verification:\n{results}"

def search_topic(topic):
    return search_web(topic)

if __name__ == "__main__":
    print("Testing internet connection via DuckDuckGo...")
    result = search_topic("capital of Japan")
    print(f"Result:\n{result}")
