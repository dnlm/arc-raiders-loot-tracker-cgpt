#!/usr/bin/env python3
for row in rows:
cells = row["cells"]
links = row["links"]
name = cells[name_idx] if name_idx < len(cells) else ""
sell_price = None
if sell_idx is not None and sell_idx < len(cells):
m = re.search(r"(\d+)", cells[sell_idx])
if m:
sell_price = int(m.group(1))
recycled_sum = 0
found_any = False
if recycles_idx is not None and recycles_idx < len(links):
for lk in links[recycles_idx]:
item_url = f"{args.base_url}{lk['href']}"
html = cached_get(item_url, force=force)
s = BeautifulSoup(html, "lxml")
p = parse_price_from_soup(s)
if p is not None:
recycled_sum += p
found_any = True
recycled_price = recycled_sum if found_any else None


decision = "Unknown"
if sell_price is not None and recycled_price is not None:
decision = "Recycle" if recycled_price > sell_price else "Sell"


out_cells = list(cells)
out_cells += [str(recycled_price) if recycled_price is not None else "", decision]
data.append({"Item": name, "row": out_cells})


Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
with open(args.out_json, "w", encoding="utf-8") as f:
json.dump({
"headers": out_headers,
"rows": [d["row"] for d in data],
"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}, f, ensure_ascii=False, indent=2)


with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
w = csv.writer(f)
w.writerow(out_headers)
for d in data:
w.writerow(d["row"])


with open(args.out_md, "w", encoding="utf-8") as f:
f.write("| " + " | ".join(out_headers) + " |\n")
f.write("|" + "---|" * len(out_headers) + "\n")
for d in data:
f.write("| " + " | ".join(c if isinstance(c, str) else str(c) for c in d["row"]) + " |\n")


print(f"Wrote {args.out_json}, {args.out_csv}, {args.out_md}")


if __name__ == "__main__":
sys.exit(main())