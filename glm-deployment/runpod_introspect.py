#!/usr/bin/env python3
"""
RunPod GraphQL Introspection — discover ALL available mutations and their input types.
"""
import os, sys, json, requests

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
if not API_KEY:
    print("Set RUNPOD_API_KEY"); sys.exit(1)

URL = f"https://api.runpod.io/graphql?api_key={API_KEY}"
H = {"Content-Type": "application/json"}

def gql(q, variables=None):
    r = requests.post(URL, headers=H, json={"query": q, "variables": variables or {}}, timeout=60)
    r.raise_for_status()
    j = r.json()
    if "errors" in j and j["errors"]:
        print("ERROR:", json.dumps(j["errors"], indent=2))
        return None
    return j.get("data")

# ─── Step 1: List ALL mutations ───────────────────────────
print("=" * 70)
print("STEP 1: ALL MUTATIONS")
print("=" * 70)

data = gql("""{ __schema { mutationType { fields { name description } } } }""")
if not data:
    sys.exit(1)

mutations = data["__schema"]["mutationType"]["fields"]
pod_mutations = [m for m in mutations if "pod" in m["name"].lower()]
other_mutations = [m for m in mutations if "pod" not in m["name"].lower()]

print(f"\nTotal mutations: {len(mutations)}")
print(f"\n--- Pod-related mutations ({len(pod_mutations)}) ---")
for m in sorted(pod_mutations, key=lambda x: x["name"]):
    desc = f" — {m['description']}" if m.get("description") else ""
    print(f"  {m['name']}{desc}")

print(f"\n--- Other mutations ({len(other_mutations)}) ---")
for m in sorted(other_mutations, key=lambda x: x["name"]):
    desc = f" — {m['description']}" if m.get("description") else ""
    print(f"  {m['name']}{desc}")

# ─── Step 2: Deep inspect pod-related mutations ───────────
print("\n" + "=" * 70)
print("STEP 2: POD MUTATION INPUT TYPES (deep)")
print("=" * 70)

for m in sorted(pod_mutations, key=lambda x: x["name"]):
    name = m["name"]
    print(f"\n{'─' * 50}")
    print(f"mutation {name}")
    
    # Get full arg details
    detail = gql(f"""{{
        __schema {{
            mutationType {{
                fields {{
                    name
                    args {{
                        name
                        type {{
                            kind name
                            ofType {{ kind name ofType {{ kind name ofType {{ kind name }} }} }}
                        }}
                    }}
                }}
            }}
        }}
    }}""")
    
    # Find this mutation's args
    for field in detail["__schema"]["mutationType"]["fields"]:
        if field["name"] == name:
            for arg in field.get("args", []):
                arg_name = arg["name"]
                t = arg["type"]
                # Unwrap type
                type_chain = []
                cur = t
                while cur:
                    if cur.get("name"):
                        type_chain.append(cur["name"])
                        break
                    if cur.get("kind"):
                        type_chain.append(cur["kind"])
                    if cur.get("ofType"):
                        cur = cur["ofType"]
                    else:
                        break
                type_str = " → ".join(type_chain) if type_chain else "?"
                print(f"  ({arg_name}: {type_str})")
                
                # If it's a named input type, get its fields
                inner_type = type_chain[-1] if type_chain else None
                if inner_type and inner_type != "JSON":
                    input_detail = gql(f"""{{
                        __type(name: "{inner_type}") {{
                            name kind
                            inputFields {{
                                name
                                type {{ kind name ofType {{ kind name }} }}
                            }}
                        }}
                    }}""")
                    if input_detail and input_detail.get("__type"):
                        itype = input_detail["__type"]
                        print(f"    └─ Input type: {itype['name']} ({itype['kind']})")
                        for f in itype.get("inputFields", []):
                            ft = f["type"]
                            ft_name = ft.get("name") or (ft.get("ofType") or {}).get("name", "?")
                            ft_kind = ft.get("kind") or (ft.get("ofType") or {}).get("kind", "")
                            req = "!" if ft.get("kind") == "NON_NULL" else ""
                            print(f"       • {f['name']}: {ft_name} ({ft_kind}){req}")
            break

# ─── Step 3: Also check for types with "Create" or "Deploy" in name ───
print("\n" + "=" * 70)
print("STEP 3: TYPES WITH 'Pod', 'Create', 'Deploy', 'Spot', 'Interrupt'")
print("=" * 70)

for keyword in ["Pod", "Create", "Deploy", "Spot", "Interrupt", "Bid"]:
    type_data = gql(f"""{{
        __type(name: "{keyword}") {{
            name kind
            inputFields {{ name type {{ kind name }} }}
            fields {{ name type {{ kind name }} }}
        }}
    }}""")
    # This won't work for partial matches, let's try differently
    pass

# Better approach: search types from the full schema
type_data = gql("""{
    __schema {
        types {
            name kind
            ... on InputObjectType { inputFields { name type { kind name ofType { kind name } } } }
        }
    }
}""")

if type_data:
    all_types = type_data["__schema"]["types"]
    interesting = [t for t in all_types if any(
        kw in (t.get("name") or "").lower()
        for kw in ["pod", "deploy", "spot", "interrupt", "bid", "create"]
    )]
    print(f"\nFound {len(interesting)} matching types:")
    for t in sorted(interesting, key=lambda x: x["name"]):
        print(f"\n  📦 {t['name']} ({t['kind']})")
        for f in t.get("inputFields", []) or []:
            ft = f["type"]
            ft_name = ft.get("name") or (ft.get("ofType") or {}).get("name", "?")
            print(f"     • {f['name']}: {ft_name}")

print("\n✅ Done. Review the output above for available mutations and their input fields.")
