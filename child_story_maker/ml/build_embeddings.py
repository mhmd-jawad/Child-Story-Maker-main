from __future__ import annotations

from pathlib import Path

from child_story_maker.common.paths import repo_root

# Single-file script: defines the tool + runs a demo/top-k check.
# Usage:
#   pip install -r requirements-embeddings.txt
#   python -m child_story_maker.ml.build_embeddings --data data/children_books.csv --out artifacts/embeddings --k 3

DEFAULT_DATA_PATH = repo_root() / "data" / "children_books.csv"
DEFAULT_OUT_DIR = repo_root() / "artifacts" / "embeddings"

def build_children_corpus_tool(
    data_path=str(DEFAULT_DATA_PATH),
    text_col="Desc",
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    out_dir=str(DEFAULT_OUT_DIR),
    base_prefix="children_books",
    batch_size=256,
    install_if_missing=False,
    cache_embeddings=True
):
    """
    Returns a dict:
      {
        "df": DataFrame,
        "embeddings": np.ndarray (N, D),
        "avg_vec": np.ndarray (D,),
        "similarity_to_average": callable(text)->float,
        "topk": callable(text,k=5)->List[(idx,score)],
        "print_topk": callable(text,k=5)->None,
        "meta_paths": {"emb":..., "avg":..., "index": ...}
      }
    """
    # optional lazy install (handy on a fresh env)
    if install_if_missing:
        try:
            import pkgutil, sys, subprocess
            def _ensure(p):
                if pkgutil.find_loader(p) is None:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", p, "-q"])
            _ensure("sentence-transformers")
            _ensure("tqdm")
            _ensure("pandas")
            _ensure("numpy")
        except Exception as e:
            print("[warn] Auto-install failed:", e)

    # local imports so this stays drop-in
    import os, math, json
    import numpy as np
    import pandas as pd
    from tqdm import tqdm
    from sentence_transformers import SentenceTransformer

    # paths
    assert os.path.exists(data_path), f"CSV not found at: {data_path}"
    os.makedirs(out_dir, exist_ok=True)
    emb_file = os.path.join(out_dir, f"{base_prefix}_embeddings.npy")
    avg_file = os.path.join(out_dir, f"{base_prefix}_avg_embedding.npy")
    idx_file = os.path.join(out_dir, f"{base_prefix}_index.json")

    # load data
    df = pd.read_csv(data_path)

    # auto-pick longest object column if needed
    if (text_col not in df.columns) or (df[text_col].dtype != "object"):
        obj_cols = [c for c in df.columns if df[c].dtype == "object"]
        if not obj_cols:
            raise ValueError("No text-like (object) columns found. Please set text_col to a string column.")
        avg_len = {c: df[c].astype(str).str.len().mean() for c in obj_cols}
        text_col = max(avg_len, key=avg_len.get)
        print(f"[auto] Using TEXT_COL = {text_col}")

    def _safe(x):
        import pandas as _pd
        return "" if _pd.isna(x) else str(x)

    df = df.copy()
    df["text"] = df[text_col].map(_safe)

    # dedupe
    before = len(df)
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)
    print(f"Loaded {before:,} rows -> {len(df):,} unique texts. Column used: {text_col}")

    texts = df["text"].astype(str).tolist()

    # embeddings
    def _batch(lst, n=batch_size):
        for i in range(0, len(lst), n):
            yield lst[i:i+n]

    def _build_or_load_embeddings(texts_, model_name_, save_path_):
        import numpy as _np, os as _os, math as _math
        from tqdm import tqdm as _tqdm
        from sentence_transformers import SentenceTransformer as _ST

        if cache_embeddings and _os.path.exists(save_path_):
            embs_ = _np.load(save_path_)
            print(f"Loaded cached embeddings: {save_path_} -> {embs_.shape}")
            return embs_

        print(f"Computing embeddings with {model_name_} ...")
        model_ = _ST(model_name_)
        out_ = []
        for chunk in _tqdm(_batch(texts_, batch_size), total=_math.ceil(len(texts_)/batch_size)):
            vecs = model_.encode(
                chunk,
                convert_to_numpy=True,
                normalize_embeddings=True  # L2-normalized -> cosine == dot
            )
            out_.append(vecs)
        embs_ = _np.vstack(out_)
        _np.save(save_path_, embs_)
        print(f"Saved per-doc embeddings -> {save_path_}")
        return embs_

    embs = _build_or_load_embeddings(texts, model_name, emb_file)
    print("Per-doc embeddings shape:", embs.shape)

    # average
    import numpy as np
    avg_vec = embs.mean(axis=0)
    norm = np.linalg.norm(avg_vec)
    if norm > 0:
        avg_vec = avg_vec / norm
    np.save(avg_file, avg_vec)
    print("Saved average embedding ->", avg_file)
    print("Average embedding shape:", avg_vec.shape, "| first 8 dims:", avg_vec[:8])

    # index for pretty printing
    import json
    def _col_values(name: str):
        if name in df.columns:
            return df[name].fillna("").astype(str).tolist()
        return [""] * len(df)

    def _top_counts(name: str, limit: int = 10):
        if name not in df.columns:
            return {}
        series = df[name].dropna().astype(str)
        return series.value_counts().head(limit).to_dict()

    stats = {
        "rows": int(len(df)),
        "avg_desc_chars": float(df["text"].str.len().mean()) if len(df) else 0.0,
        "interest_age_counts": _top_counts("Inerest_age"),
        "reading_age_counts": _top_counts("Reading_age"),
    }
    meta = {
        "rows": int(len(df)),
        "title": _col_values("Title"),
        "author": _col_values("Author"),
        "interest_age": _col_values("Inerest_age"),
        "reading_age": _col_values("Reading_age"),
        "text_preview": [t[:180] for t in texts],
        "stats": stats,
        "model_name": model_name,
    }
    with open(idx_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    print("Saved index ->", idx_file)

    # helpers
    _model_cache = {"model": None}
    def _get_model():
        if _model_cache["model"] is None:
            from sentence_transformers import SentenceTransformer
            _model_cache["model"] = SentenceTransformer(model_name)
        return _model_cache["model"]

    def similarity_to_average(text: str) -> float:
        q = _get_model().encode([text], convert_to_numpy=True, normalize_embeddings=True)
        return float(np.dot(q, avg_vec).item())  # cosine (normalized)

    def topk(text: str, k: int = 5):
        q = _get_model().encode([text], convert_to_numpy=True, normalize_embeddings=True)
        sims = embs @ q.T
        sims = sims.ravel()
        k_eff = int(min(max(k, 1), len(sims)))
        idx = np.argpartition(-sims, range(k_eff))[:k_eff]
        idx = idx[np.argsort(-sims[idx])]
        return [(int(i), float(sims[i])) for i in idx]

    def print_topk(text: str, k: int = 5):
        hits = topk(text, k=k)
        for r, (i, s) in enumerate(hits, 1):
            title = df.iloc[i]["Title"] if "Title" in df.columns else ""
            snippet = df.iloc[i]["text"][:180].replace("\n", " ")
            print(f"{r:>2}. score={s:.4f} | {title}\n    {snippet}\n")

    return {
        "df": df,
        "embeddings": embs,
        "avg_vec": avg_vec,
        "similarity_to_average": similarity_to_average,
        "topk": topk,
        "print_topk": print_topk,
        "meta_paths": {"emb": emb_file, "avg": avg_file, "index": idx_file},
    }

# ---------- CLI / Runner ----------
if __name__ == "__main__":
    import argparse, os, sys
    parser = argparse.ArgumentParser(description="Children stories embeddings + average + cosine compare")
    parser.add_argument("--data", dest="data_path", default=str(DEFAULT_DATA_PATH), help="Path to CSV")
    parser.add_argument("--text-col", dest="text_col", default="Desc", help="Text column name (auto-detects if missing)")
    parser.add_argument("--out", dest="out_dir", default=str(DEFAULT_OUT_DIR), help="Output directory")
    parser.add_argument("--prefix", dest="base_prefix", default="children_books", help="Output file prefix")
    parser.add_argument("--k", dest="k", type=int, default=5, help="Top-k neighbors to print")
    parser.add_argument("--install", action="store_true", help="Try to auto-install deps if missing")
    args = parser.parse_args()

    tool = build_children_corpus_tool(
        data_path=args.data_path,
        text_col=args.text_col,
        out_dir=args.out_dir,
        base_prefix=args.base_prefix,
        install_if_missing=args.install
    )

    # demo text (you can change or pass your own by editing below)
    gpt_text = """Eli the Elephant and the Big MoveA gentle, rhyming bedtime story about finding home wherever you go---- ###Page_1Under the mango, little Eli would play,Splashing the puddles at break of day."Time to move, dear," said Mama with a smile,"Our family is traveling for a little while."---- ###Page_2"But why must we go? I like it here!""The grass is low, the rain's not near.We follow the river when waters run slow,To find fresh leaves and help new flowers grow."---- ###Page_3Eli packed his trunk-what funny word play!He tucked in a pebble and leaf for the way.He hugged all his friends-Bird, Monkey, and Bee,"I'll trumpet you notes! Please trumpet to me!"---- ###Page_4He felt a bit wobbly, both brave and blue,But holding Mom's tail made courage grow too.Step after step, they went nice and slow,...Some things were new, some stayed the same,Hugs, songs, and stories at bedtime came."Home is our hearts, wherever we roam,""With family and friends, we carry our home.\""""


    print("\nSimilarity to AVERAGE:", round(tool["similarity_to_average"](gpt_text), 4))
    print("\nTop neighbors:")
    tool["print_topk"](gpt_text, k=args.k)
