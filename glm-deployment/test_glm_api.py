"""
Test script for GLM-4.7-Flash API on RunPod.
Usage: python test_glm_api.py [BASE_URL] [mode]

Modes: speed, stress, full
  speed  - Speed benchmark (default)
  stress - Hard coding stress test
  full   - Connection, streaming, coding, agent tests

Examples:
  python test_glm_api.py                                    # Speed test
  python test_glm_api.py https://your-pod-8000.proxy.runpod.net/v1 stress
  python test_glm_api.py http://localhost:8080/v1 speed     # Via local proxy
"""

import sys
import time
from openai import OpenAI

# Your RunPod GLM endpoint — pass as argument or set here
# Use port 8000 proxy URL from RunPod (NOT the web terminal URL)
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://olvdw1yjuoa1mz-8000.proxy.runpod.net/v1"
MODEL = "/workspace/models/glm-4.7-flash-4bit"

client = OpenAI(
    base_url=BASE_URL,
    api_key="not-needed"
)


def test_connection():
    """Test basic connectivity."""
    print("🔌 Testing connection...")
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Say hello in one word"}],
            max_tokens=20
        )
        # Handle both string and object responses
        if isinstance(response, str):
            print(f"✅ Connected! Response: {response}")
        else:
            print(f"✅ Connected! Response: {response.choices[0].message.content}")
            print(f"   Tokens: {response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_streaming():
    """Test streaming response."""
    print("\n🌊 Testing streaming...")
    try:
        start = time.time()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Write a Python function to reverse a string"}],
            stream=True,
            max_tokens=256
        )
        
        print("📝 Response: ", end="", flush=True)
        full_text = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                print(token, end="", flush=True)
                full_text += token
        
        elapsed = time.time() - start
        print(f"\n⏱️  Time: {elapsed:.2f}s")
        print(f"✅ Streaming works!")
        return True
    except Exception as e:
        print(f"❌ Streaming failed: {e}")
        return False


def test_coding():
    """Test coding capability."""
    print("\n💻 Testing coding capability...")
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are an expert Python developer. Return only code, no explanation."},
                {"role": "user", "content": "Write a FastAPI endpoint that accepts a JSON body with 'name' and 'email' and returns a success response"}
            ],
            max_tokens=512,
            temperature=0.2
        )
        
        if isinstance(response, str):
            content = response
            print(f"📝 Response:\n{content}")
        else:
            content = response.choices[0].message.content
            print(f"📝 Response:\n{content}")
            print(f"   Tokens: {response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion")
        print(f"✅ Coding test passed!")
        return True
    except Exception as e:
        print(f"❌ Coding test failed: {e}")
        return False


def test_agent_style():
    """Test agent-style multi-turn conversation."""
    print("\n🤖 Testing agent-style conversation...")
    try:
        messages = [
            {"role": "system", "content": "You are a helpful coding agent. Be concise."},
            {"role": "user", "content": "Read this file and tell me what it does: def add(a, b): return a + b"},
        ]
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=128,
            temperature=0.1
        )
        
        if isinstance(response, str):
            reply = response
        else:
            reply = response.choices[0].message.content
        print(f"🤖 Agent: {reply}")
        
        # Follow-up
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": "Now add error handling to it"})
        
        response2 = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=256,
            temperature=0.1
        )
        
        if isinstance(response2, str):
            reply2 = response2
        else:
            reply2 = response2.choices[0].message.content
        print(f"🤖 Agent (follow-up): {reply2}")
        print(f"✅ Multi-turn conversation works!")
        return True
    except Exception as e:
        print(f"❌ Agent test failed: {e}")
        return False


def test_speed():
    """Benchmark response speed: TTFT, total time, tokens/sec."""
    print("\n⚡ Running Speed Benchmark...")
    print("-" * 50)

    prompts = [
        ("Short", "Say hello in one sentence.", 50),
        ("Medium", "Explain what a REST API is in 3 bullet points.", 200),
        ("Coding", "Write a Python function to compute fibonacci numbers with memoization.", 300),
        ("Long", "Write a detailed code review checklist for a Python FastAPI project. Cover security, performance, testing, and code style.", 800),
    ]

    rounds = 3
    results = []

    for name, prompt, max_tokens in prompts:
        print(f"\n📊 [{name}] \"{prompt[:60]}...\"")
        round_ttft = []
        round_total = []
        round_tps = []

        for i in range(rounds):
            try:
                # Streaming request to measure TTFT and tokens/sec
                start = time.time()
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    stream=True,
                    temperature=0.1,
                )

                first_token_time = None
                full_text = ""
                token_count = 0

                for chunk in response:
                    now = time.time()
                    if chunk.choices and chunk.choices[0].delta.content:
                        if first_token_time is None:
                            first_token_time = now
                        full_text += chunk.choices[0].delta.content
                        token_count += 1

                # Also get usage info from a non-streaming call for accurate token counts
                # (vLLM streaming doesn't always return usage)
                elapsed = time.time() - start
                ttft = (first_token_time - start) if first_token_time else elapsed

                # Estimate tokens (rough: ~4 chars per token for English)
                estimated_tokens = max(token_count, len(full_text) / 4)
                tps = estimated_tokens / elapsed if elapsed > 0 else 0

                round_ttft.append(ttft)
                round_total.append(elapsed)
                round_tps.append(tps)

                bar_len = int(elapsed * 5)
                bar = "█" * bar_len
                print(f"  Round {i+1}: TTFT={ttft:.2f}s  Total={elapsed:.2f}s  ~{tps:.0f} tok/s  {bar}")

            except Exception as e:
                print(f"  Round {i+1}: ❌ {e}")

        if round_ttft:
            avg_ttft = sum(round_ttft) / len(round_ttft)
            avg_total = sum(round_total) / len(round_total)
            avg_tps = sum(round_tps) / len(round_tps)
            results.append((name, avg_ttft, avg_total, avg_tps))
            print(f"  📈 Avg: TTFT={avg_ttft:.2f}s  Total={avg_total:.2f}s  ~{avg_tps:.0f} tok/s")
        else:
            results.append((name, None, None, None))
            print(f"  ❌ All rounds failed")

    # Summary table
    print("\n" + "=" * 70)
    print("⚡ SPEED BENCHMARK RESULTS")
    print("=" * 70)
    print(f"{'Prompt':<10} {'TTFT':>10} {'Total':>10} {'Tokens/s':>12}")
    print("-" * 70)
    for name, ttft, total, tps in results:
        if ttft is not None:
            print(f"{name:<10} {ttft:>9.2f}s {total:>9.2f}s {tps:>10.0f} t/s")
        else:
            print(f"{name:<10} {'FAILED':>10}")
    print("=" * 70)

    # Overall
    valid = [(n, t, ttl, tps) for n, t, ttl, tps in results if t is not None]
    if valid:
        overall_ttft = sum(t for _, t, _, _ in valid) / len(valid)
        overall_tps = sum(tps for _, _, _, tps in valid) / len(valid)
        print(f"📊 Overall: Avg TTFT={overall_ttft:.2f}s  Avg Speed=~{overall_tps:.0f} tokens/sec")

    return len(valid) > 0


def test_stress_coding():
    """Stress test with hard coding tasks — complex, multi-step, real-world."""
    print("\n🔥 STRESS CODING TEST — Real-World Hard Tasks")
    print("=" * 70)

    tasks = [
        {
            "name": "FastAPI Full App",
            "prompt": """Write a complete FastAPI application with:
1. A Pydantic model for a Todo item (id, title, description, completed, created_at)
2. CRUD endpoints (GET all, GET by id, POST, PUT, DELETE)
3. In-memory storage using a dict
4. Proper error handling with HTTPException
5. A health check endpoint
Return only the complete working code, no explanations.""",
            "max_tokens": 1000,
        },
        {
            "name": "React Hook",
            "prompt": """Write a custom React hook `useDebounce` that:
1. Takes a value and a delay in milliseconds
2. Returns the debounced value
3. Cleans up the timeout on unmount
4. Handles rapid changes correctly
Also write a `useSearch` hook that uses useDebounce to debounce a search query and fetches results from an API.
Return only the complete TypeScript code, no explanations.""",
            "max_tokens": 800,
        },
        {
            "name": "Database Migration",
            "prompt": """Write a Python function that handles database migrations:
1. A Migration class with up() and down() methods
2. A MigrationRunner that tracks applied migrations in a 'migrations' table
3. Support for running migrations up and rolling back
4. Transaction support — if a migration fails, rollback
5. A decorator @migration(version, description) to register migrations
Use async/await with asyncpg. Return only the complete working code.""",
            "max_tokens": 1000,
        },
        {
            "name": "Algorithm Challenge",
            "prompt": """Implement a LRU (Least Recently Used) Cache in Python with:
1. O(1) get and put operations
2. A capacity limit that evicts the least recently used item
3. Type hints for all methods
4. A __repr__ method showing current cache state
5. Thread-safe implementation using locks
6. Unit tests using pytest
Return only the complete working code.""",
            "max_tokens": 1000,
        },
        {
            "name": "Error Recovery",
            "prompt": """Write a Python decorator `@retry` that:
1. Retries a function on specified exceptions (default: Exception)
2. Takes max_retries, delay, backoff_factor, max_delay parameters
3. Supports exponential backoff with jitter
4. Logs each retry attempt with the exception
5. Raises a RetryError with the last exception after all retries exhausted
6. Preserves the original function signature using functools.wraps
Also write a `@circuit_breaker` decorator that stops calling a function after N failures within a time window.
Return only the complete working code.""",
            "max_tokens": 1200,
        },
    ]

    results = []

    for task in tasks:
        name = task["name"]
        prompt = task["prompt"]
        max_tokens = task["max_tokens"]

        print(f"\n📝 [{name}]")
        print(f"   Max tokens: {max_tokens}")

        try:
            start = time.time()
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert senior software engineer. Return only clean, production-ready code. No explanations, no markdown headers, just code."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.2,
                stream=True,
            )

            first_token_time = None
            full_text = ""
            chunk_count = 0

            for chunk in response:
                now = time.time()
                if chunk.choices and chunk.choices[0].delta.content:
                    if first_token_time is None:
                        first_token_time = now
                    full_text += chunk.choices[0].delta.content
                    chunk_count += 1

            elapsed = time.time() - start
            ttft = (first_token_time - start) if first_token_time else elapsed
            estimated_tokens = max(chunk_count, len(full_text) / 4)
            tps = estimated_tokens / elapsed if elapsed > 0 else 0

            # Quality checks
            has_code = any(kw in full_text for kw in ["def ", "class ", "import ", "function ", "const ", "async "])
            has_error_handling = any(kw in full_text for kw in ["try:", "except", "Error", "raise", "catch"])
            code_length = len(full_text)

            quality_score = 0
            if has_code: quality_score += 1
            if has_error_handling: quality_score += 1
            if code_length > 500: quality_score += 1
            if code_length > 1000: quality_score += 1
            if tps > 30: quality_score += 1

            stars = "⭐" * quality_score + "☆" * (5 - quality_score)

            print(f"   ✅ Done in {elapsed:.1f}s")
            print(f"   TTFT: {ttft:.2f}s | Speed: ~{tps:.0f} tok/s | Output: {code_length} chars")
            print(f"   Quality: {stars} ({quality_score}/5)")
            print(f"   Preview: {full_text[:150].replace(chr(10), ' ')}...")

            results.append({
                "name": name,
                "ttft": ttft,
                "total": elapsed,
                "tps": tps,
                "chars": code_length,
                "quality": quality_score,
                "success": True,
            })

        except Exception as e:
            print(f"   ❌ FAILED: {e}")
            results.append({"name": name, "success": False, "error": str(e)})

    # Summary
    print("\n" + "=" * 70)
    print("🔥 STRESS CODING TEST — SUMMARY")
    print("=" * 70)
    print(f"{'Task':<20} {'TTFT':>8} {'Total':>8} {'tok/s':>8} {'Chars':>8} {'Score':>8}")
    print("-" * 70)

    total_quality = 0
    total_tps = 0
    success_count = 0

    for r in results:
        if r["success"]:
            print(f"{r['name']:<20} {r['ttft']:>7.2f}s {r['total']:>7.1f}s {r['tps']:>7.0f} {r['chars']:>8} {r['quality']:>5}/5")
            total_quality += r["quality"]
            total_tps += r["tps"]
            success_count += 1
        else:
            print(f"{r['name']:<20} {'FAILED':>8}")

    if success_count > 0:
        print("-" * 70)
        avg_tps = total_tps / success_count
        avg_quality = total_quality / success_count
        print(f"{'AVERAGE':<20} {'':>8} {'':>8} {avg_tps:>7.0f} {'':>8} {avg_quality:>5.1f}/5")
        print(f"\n🏆 Overall: {success_count}/{len(tasks)} tasks passed | Avg {avg_tps:.0f} tok/s | Quality {avg_quality:.1f}/5")

    print("=" * 70)
    return success_count == len(tasks)


if __name__ == "__main__":
    mode = sys.argv[2] if len(sys.argv) > 2 else "speed"

    print("=" * 50)
    print("GLM-4-9B API Test Suite")
    print(f"Endpoint: {BASE_URL}")
    print(f"Model: {MODEL}")
    print(f"Mode: {mode}")
    print("=" * 50)

    if mode == "speed":
        success = test_speed()
        sys.exit(0 if success else 1)
    elif mode == "stress":
        success = test_stress_coding()
        sys.exit(0 if success else 1)
    else:
        results = []
        results.append(("Connection", test_connection()))
        results.append(("Streaming", test_streaming()))
        results.append(("Coding", test_coding()))
        results.append(("Agent-style", test_agent_style()))

        print("\n" + "=" * 50)
        print("RESULTS:")
        for name, passed in results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status} - {name}")
        print("=" * 50)

        all_passed = all(r[1] for r in results)
        sys.exit(0 if all_passed else 1)
