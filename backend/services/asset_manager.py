from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional
from urllib.parse import quote_plus

import httpx

from config import (
    ANATOMY_LIBRARY_DIR,
    BLENDERKIT_CACHE_DIR,
    CUSTOM_LIBRARY_DIR,
    MIXAMO_LIBRARY_DIR,
    POLYHAVEN_CACHE_DIR,
)
from database import get_settings

POLYHAVEN_API = "https://api.polyhaven.com"
POLYHAVEN_HEADERS = {"User-Agent": "StickKnowledge3DStudio/1.0"}
BLENDERKIT_SEARCH_API = "https://www.blenderkit.com/api/v1/search/"
NIH3D_API = "https://3d.nih.gov/api/entries"

MIXAMO_TAGS = [
    "idle",
    "talking",
    "pointing",
    "holding",
    "phone",
    "surprised",
    "walking",
    "running",
    "sitting",
    "eating",
    "drinking",
    "thinking",
    "waving",
    "falling",
    "coughing",
]

LogCallback = Optional[Callable[[str, str], Coroutine[Any, Any, None]]]


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48] or "asset"


class AssetManager:
    """
    100% Free, Zero-Sketchfab 6-Tier 3D Asset Resolver:
      Tier 1: BlenderKit Free Native `.blend` Models & PBR Materials
      Tier 2: Poly Haven Live API (CC0 models, textures, HDRIs — ZERO auth)
      Tier 3: Local Mixamo & Custom Library (`assets_library/mixamo/` & `custom/`) + MPFB2 detection
      Tier 4: NIH 3D Anatomy Library (`3d.nih.gov` open-access `.glb` anatomical meshes)
      Tier 5: Free AI 3D Fallback (`gradio_client` -> HF `tencent/Hunyuan3D-2` or `microsoft/TRELLIS`)
      Tier 6: Procedural `bpy` Fallback (graceful, never crashes)
    """

    def __init__(self) -> None:
        self._polyhaven_index_cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Local Mixamo & Custom Library Scanner
    # ------------------------------------------------------------------
    def scan_local_libraries(self) -> dict[str, Any]:
        mixamo_items = self._scan_folder(MIXAMO_LIBRARY_DIR, source="mixamo")
        custom_items = self._scan_folder(CUSTOM_LIBRARY_DIR, source="custom")
        anatomy_items = self._scan_folder(ANATOMY_LIBRARY_DIR, source="nih3d")
        polyhaven_items = self._scan_folder(POLYHAVEN_CACHE_DIR, source="polyhaven")
        blenderkit_items = self._scan_folder(BLENDERKIT_CACHE_DIR, source="blenderkit")

        catalog = {
            "mixamo": mixamo_items,
            "custom": custom_items,
            "anatomy": anatomy_items,
            "polyhaven_cache": polyhaven_items,
            "blenderkit_cache": blenderkit_items,
        }
        (MIXAMO_LIBRARY_DIR / "catalog.json").write_text(
            json.dumps({"items": mixamo_items}, indent=2), encoding="utf-8"
        )
        return catalog

    def _scan_folder(self, folder: Path, source: str) -> list[dict[str, Any]]:
        exts = {".fbx", ".glb", ".gltf", ".blend", ".obj", ".hdr", ".exr"}
        items: list[dict[str, Any]] = []
        if not folder.exists():
            return items
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix.lower() in exts:
                stem_lower = p.stem.lower()
                tokens = re.findall(r"[a-z0-9]+", stem_lower)
                tags = [t for t in MIXAMO_TAGS if t in stem_lower]
                if not tags:
                    tags = tokens[:4]
                items.append(
                    {
                        "name": p.stem,
                        "filename": p.name,
                        "path": str(p),
                        "ext": p.suffix.lower(),
                        "size_kb": round(p.stat().st_size / 1024, 1),
                        "source": source,
                        "tags": tags,
                        "character_type": _infer_character_type(stem_lower),
                    }
                )
        return items

    def _match_local_library(self, query: str, category: str) -> Optional[dict[str, Any]]:
        catalog = self.scan_local_libraries()
        q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        if not q_tokens:
            return None

        pools: list[dict[str, Any]] = []
        if category == "character":
            pools = catalog["mixamo"] + catalog["custom"]
        elif category == "anatomy":
            pools = catalog["anatomy"] + catalog["custom"]
        else:
            pools = catalog["custom"] + catalog["blenderkit_cache"] + catalog["polyhaven_cache"]

        best = None
        best_score = 0
        for item in pools:
            hay = set(re.findall(r"[a-z0-9]+", item["name"].lower())) | set(item.get("tags", []))
            score = len(q_tokens & hay)
            # If character query has any Mixamo character available, give baseline score
            if category == "character" and item["source"] == "mixamo" and score == 0:
                score = 1
            if score > best_score:
                best_score = score
                best = item
        return best if best_score > 0 else None

    # ------------------------------------------------------------------
    # Tier 1: BlenderKit Free API
    # ------------------------------------------------------------------
    async def search_blenderkit_free(
        self, query: str, asset_type: str = "model", limit: int = 8
    ) -> list[dict[str, Any]]:
        settings = get_settings()
        bk_key = settings.get("blenderkit_api_key", "").strip()
        params = {
            "query": f"{query} order:_score is_free:true asset_type:{asset_type}",
            "page_size": limit,
        }
        headers = {"User-Agent": "StickKnowledge3DStudio/1.0"}
        if bk_key:
            headers["Authorization"] = f"Bearer {bk_key}"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                r = await client.get(BLENDERKIT_SEARCH_API, params=params, headers=headers)
                if r.status_code != 200:
                    # Try alternate simpler query format
                    r = await client.get(
                        f"{BLENDERKIT_SEARCH_API}?query={quote_plus(query)}&asset_type={asset_type}&is_free=true",
                        headers=headers,
                    )
                if r.status_code != 200:
                    return []
                data = r.json()
                results = []
                for item in data.get("results", [])[:limit]:
                    if item.get("isFree") is False:
                        continue
                    files = item.get("files", [])
                    blend_file = next(
                        (f for f in files if f.get("fileType") in ("blend", "resolution_2K", "resolution_1K")),
                        files[0] if files else None,
                    )
                    results.append(
                        {
                            "id": item.get("id") or item.get("assetBaseId"),
                            "asset_base_id": item.get("assetBaseId"),
                            "name": item.get("name", query),
                            "asset_type": item.get("assetType", asset_type),
                            "thumbnail": item.get("thumbnailSmallUrl") or item.get("thumbnailMiddleUrl", ""),
                            "download_url": (blend_file or {}).get("downloadUrl", ""),
                            "license": item.get("license", "royalty_free"),
                            "source": "blenderkit",
                        }
                    )
                return results
        except Exception:
            return []

    async def _download_blenderkit_asset(
        self, item: dict[str, Any], target_assets_dir: Path
    ) -> Optional[Path]:
        dl_url = item.get("download_url")
        if not dl_url:
            return None
        settings = get_settings()
        bk_key = settings.get("blenderkit_api_key", "").strip()
        headers = {"User-Agent": "StickKnowledge3DStudio/1.0"}
        if bk_key:
            headers["Authorization"] = f"Bearer {bk_key}"

        slug = _slugify(item.get("name", "bk_asset"))
        cache_file = BLENDERKIT_CACHE_DIR / f"bk_{slug}_{str(item.get('id',''))[:8]}.blend"
        dest_file = target_assets_dir / cache_file.name

        if cache_file.is_file() and cache_file.stat().st_size > 1024:
            shutil.copy2(cache_file, dest_file)
            return dest_file

        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                # BlenderKit downloadUrl returns JSON with signed filePath or streams directly
                r = await client.get(dl_url, headers=headers)
                if r.status_code != 200:
                    return None
                ctype = r.headers.get("content-type", "")
                if "application/json" in ctype:
                    meta = r.json()
                    signed = meta.get("filePath") or meta.get("url")
                    if not signed:
                        return None
                    r2 = await client.get(signed)
                    if r2.status_code != 200 or len(r2.content) < 1024:
                        return None
                    cache_file.write_bytes(r2.content)
                else:
                    if len(r.content) < 1024:
                        return None
                    cache_file.write_bytes(r.content)

            # Verify magic bytes for .blend or gzip/zstd compressed .blend
            header_bytes = cache_file.read_bytes()[:12]
            if not (
                header_bytes.startswith(b"BLENDER")
                or header_bytes[:2] == b"\x1f\x8b"
                or header_bytes[:4] == b"\x28\xb5\x2f\xfd"
            ):
                cache_file.unlink(missing_ok=True)
                return None

            shutil.copy2(cache_file, dest_file)
            return dest_file
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Tier 2: Poly Haven Live API (ZERO AUTH, CC0)
    # ------------------------------------------------------------------
    async def search_polyhaven(
        self, query: str, asset_type: str = "models", limit: int = 8
    ) -> list[dict[str, Any]]:
        """asset_type in {'models', 'textures', 'hdris'}"""
        ph_type = asset_type
        if ph_type in ("prop", "model"):
            ph_type = "models"
        elif ph_type in ("material", "texture"):
            ph_type = "textures"
        elif ph_type == "hdri":
            ph_type = "hdris"

        if ph_type not in self._polyhaven_index_cache:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    r = await client.get(
                        f"{POLYHAVEN_API}/assets",
                        params={"t": ph_type},
                        headers=POLYHAVEN_HEADERS,
                    )
                    r.raise_for_status()
                    self._polyhaven_index_cache[ph_type] = r.json()
            except Exception:
                return []

        index = self._polyhaven_index_cache.get(ph_type, {})
        q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        scored: list[tuple[int, str, dict[str, Any]]] = []

        for slug, info in index.items():
            name = str(info.get("name", slug)).lower()
            tags = [str(t).lower() for t in info.get("tags", [])]
            cats = [str(c).lower() for c in info.get("categories", [])]
            hay_tokens = set(re.findall(r"[a-z0-9]+", f"{slug} {name} {' '.join(tags)} {' '.join(cats)}"))
            overlap = len(q_tokens & hay_tokens)
            if overlap > 0:
                bonus = 2 if query.lower() in name else 0
                scored.append((overlap * 10 + bonus, slug, info))

        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for _, slug, info in scored[:limit]:
            out.append(
                {
                    "id": slug,
                    "name": info.get("name", slug),
                    "asset_type": ph_type,
                    "thumbnail": f"https://cdn.polyhaven.com/asset_img/thumbs/{slug}.png?height=180",
                    "license": "CC0",
                    "source": "polyhaven",
                }
            )
        return out

    async def _download_polyhaven_asset(
        self, slug: str, ph_type: str, target_assets_dir: Path
    ) -> Optional[Path]:
        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                r = await client.get(
                    f"{POLYHAVEN_API}/files/{slug}", headers=POLYHAVEN_HEADERS
                )
                r.raise_for_status()
                files_data = r.json()

                url = None
                ext = ".gltf"
                include: dict[str, Any] = {}  # side files (textures/...) the .blend/.gltf references
                if ph_type == "models":
                    # Prefer gltf 2k/1k or blend 2k/1k
                    gltf_node = files_data.get("gltf", {})
                    blend_node = files_data.get("blend", {})
                    for res in ("2k", "1k", "4k"):
                        if res in blend_node and "blend" in blend_node[res]:
                            url = blend_node[res]["blend"].get("url")
                            include = blend_node[res]["blend"].get("include") or {}
                            ext = ".blend"
                            break
                        if res in gltf_node and "gltf" in gltf_node[res]:
                            url = gltf_node[res]["gltf"].get("url")
                            include = gltf_node[res]["gltf"].get("include") or {}
                            ext = ".gltf"
                            break
                elif ph_type == "hdris":
                    hdri_node = files_data.get("hdri", {})
                    for res in ("2k", "1k", "4k"):
                        if res in hdri_node and "hdr" in hdri_node[res]:
                            url = hdri_node[res]["hdr"].get("url")
                            ext = ".hdr"
                            break
                elif ph_type == "textures":
                    blend_node = files_data.get("blend", {})
                    for res in ("2k", "1k"):
                        if res in blend_node and "blend" in blend_node[res]:
                            url = blend_node[res]["blend"].get("url")
                            include = blend_node[res]["blend"].get("include") or {}
                            ext = ".blend"
                            break

                if not url:
                    return None

                cache_file = POLYHAVEN_CACHE_DIR / f"ph_{slug}{ext}"
                dest_file = target_assets_dir / cache_file.name

                if not (cache_file.is_file() and cache_file.stat().st_size > 1024):
                    dl = await client.get(url, headers=POLYHAVEN_HEADERS)
                    dl.raise_for_status()
                    cache_file.write_bytes(dl.content)

                shutil.copy2(cache_file, dest_file)
                # Poly Haven .blend/.gltf files load their textures from relative paths
                # (e.g. textures/x_diff_2k.jpg); without them the model renders pink.
                for rel, meta in include.items():
                    rel_path = Path(rel)
                    if rel_path.is_absolute() or ".." in rel_path.parts or not (meta or {}).get("url"):
                        continue
                    cached = POLYHAVEN_CACHE_DIR / rel_path
                    if not (cached.is_file() and cached.stat().st_size > 0):
                        cached.parent.mkdir(parents=True, exist_ok=True)
                        tex = await client.get(meta["url"], headers=POLYHAVEN_HEADERS)
                        tex.raise_for_status()
                        cached.write_bytes(tex.content)
                    out = target_assets_dir / rel_path
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if not out.is_file():
                        shutil.copy2(cached, out)
                return dest_file
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Tier 4: NIH 3D Anatomy Library (3d.nih.gov)
    # ------------------------------------------------------------------
    async def search_and_fetch_nih3d(
        self, query: str, target_assets_dir: Path
    ) -> Optional[dict[str, Any]]:
        # Check cached anatomy folder first
        slug = _slugify(query)
        for existing in ANATOMY_LIBRARY_DIR.glob("*.glb"):
            if slug in existing.stem.lower() or any(
                tok in existing.stem.lower() for tok in slug.split("_") if len(tok) > 3
            ):
                dest = target_assets_dir / existing.name
                shutil.copy2(existing, dest)
                return {
                    "source": "nih3d",
                    "local_path": str(dest),
                    "display_name": existing.stem,
                    "license": "NIH Open Access",
                }

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                r = await client.get(
                    NIH3D_API,
                    params={"search": query, "page_size": 5},
                    headers={"User-Agent": "StickKnowledge3DStudio/1.0", "Accept": "application/json"},
                )
                if r.status_code != 200:
                    return None
                data = r.json()
                entries = data.get("results", data) if isinstance(data, dict) else data
                if not isinstance(entries, list):
                    return None
                for entry in entries[:4]:
                    title = entry.get("title", query)
                    # Look for direct GLB download link in entry files
                    files = entry.get("files", []) or entry.get("downloads", [])
                    glb_url = None
                    for f in files:
                        u = f.get("url") or f.get("file") or ""
                        if ".glb" in u.lower():
                            glb_url = u
                            break
                    if glb_url:
                        dl = await client.get(glb_url)
                        if dl.status_code == 200 and len(dl.content) > 2048:
                            cache_file = ANATOMY_LIBRARY_DIR / f"nih_{_slugify(title)}.glb"
                            cache_file.write_bytes(dl.content)
                            dest = target_assets_dir / cache_file.name
                            shutil.copy2(cache_file, dest)
                            return {
                                "source": "nih3d",
                                "local_path": str(dest),
                                "display_name": title,
                                "license": "NIH Open Access",
                            }
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------
    # Tier 5: Hugging Face Free AI 3D Generator Fallback (gradio_client)
    # ------------------------------------------------------------------
    async def generate_hf_ai_3d(
        self, prompt: str, target_assets_dir: Path
    ) -> Optional[dict[str, Any]]:
        """
        Optional free AI 3D fallback using gradio_client -> tencent/Hunyuan3D-2
        or microsoft/TRELLIS public Spaces. Runs in a thread with a strict timeout
        so the pipeline never stalls if Spaces are busy.
        """
        settings = get_settings()
        hf_token = settings.get("huggingface_token", "").strip() or None

        def _sync_call() -> Optional[str]:
            try:
                from gradio_client import Client
            except Exception:
                return None

            spaces = [
                ("tencent/Hunyuan3D-2", "/shape_generation"),
                ("microsoft/TRELLIS", "/generate_and_extract_glb"),
            ]
            for space_id, api_name in spaces:
                try:
                    client = Client(space_id, hf_token=hf_token)
                    res = client.predict(prompt, api_name=api_name)
                    # Extract .glb path from tuple/dict/str response
                    candidates = res if isinstance(res, (list, tuple)) else [res]
                    for item in candidates:
                        path_str = item.get("value") if isinstance(item, dict) else str(item)
                        if path_str and path_str.lower().endswith(".glb") and Path(path_str).is_file():
                            return path_str
                except Exception:
                    continue
            return None

        try:
            glb_tmp = await asyncio.wait_for(asyncio.to_thread(_sync_call), timeout=45.0)
            if glb_tmp and Path(glb_tmp).is_file():
                dest = target_assets_dir / f"hf3d_{_slugify(prompt)}.glb"
                shutil.copy2(glb_tmp, dest)
                return {
                    "source": "huggingface",
                    "local_path": str(dest),
                    "display_name": f"AI 3D: {prompt}",
                    "license": "Generated (HF Spaces)",
                }
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------
    # Master Multi-Tier Resolver
    # ------------------------------------------------------------------
    async def resolve_asset(
        self,
        asset_req: dict[str, Any],
        target_assets_dir: Path,
        *,
        allow_hf_fallback: bool = False,
        log: LogCallback = None,
    ) -> dict[str, Any]:
        target_assets_dir.mkdir(parents=True, exist_ok=True)
        query = str(asset_req.get("query", "")).strip()
        category = str(asset_req.get("category", "prop")).lower()
        updated = dict(asset_req)

        async def _emit(msg: str) -> None:
            if log:
                await log("asset", msg)

        # Tier 3 priority for human characters (Mixamo / Custom)
        if category == "character":
            local_match = self._match_local_library(query, "character")
            if local_match:
                src = Path(local_match["path"])
                dest = target_assets_dir / src.name
                shutil.copy2(src, dest)
                await _emit(f"[Mixamo/Local] Matched character '{local_match['name']}' for '{query}'")
                updated.update(
                    {
                        "resolved_source": local_match["source"],
                        "local_path": str(dest),
                        "display_name": local_match["name"],
                        "license": "Local Library",
                        "status": "resolved",
                    }
                )
                return updated

        # Tier 4 priority for anatomy (NIH 3D)
        if category == "anatomy":
            nih = await self.search_and_fetch_nih3d(query, target_assets_dir)
            if nih:
                await _emit(f"[NIH 3D] Fetched anatomy model '{nih['display_name']}' for '{query}'")
                updated.update(
                    {
                        "resolved_source": "nih3d",
                        "local_path": nih["local_path"],
                        "display_name": nih["display_name"],
                        "license": nih["license"],
                        "status": "resolved",
                    }
                )
                return updated

        # Check Local Custom cache before network
        local_any = self._match_local_library(query, category)
        if local_any:
            src = Path(local_any["path"])
            dest = target_assets_dir / src.name
            shutil.copy2(src, dest)
            await _emit(f"[Local Cache] Reused '{local_any['name']}' for '{query}'")
            updated.update(
                {
                    "resolved_source": local_any["source"],
                    "local_path": str(dest),
                    "display_name": local_any["name"],
                    "license": "Local Cache",
                    "status": "resolved",
                }
            )
            return updated

        # Tier 1: BlenderKit Free Native `.blend` Models & Materials
        bk_type = "material" if category == "material" else ("hdr" if category == "hdri" else "model")
        bk_hits = await self.search_blenderkit_free(query, asset_type=bk_type, limit=4)
        for hit in bk_hits:
            downloaded = await self._download_blenderkit_asset(hit, target_assets_dir)
            if downloaded:
                await _emit(f"[BlenderKit Free] Downloaded '{hit['name']}' -> {downloaded.name}")
                updated.update(
                    {
                        "resolved_source": "blenderkit",
                        "local_path": str(downloaded),
                        "display_name": hit["name"],
                        "license": hit.get("license", "Free"),
                        "status": "resolved",
                    }
                )
                return updated

        # Tier 2: Poly Haven Live API (CC0, zero auth)
        ph_type = "textures" if category == "material" else ("hdris" if category == "hdri" else "models")
        ph_hits = await self.search_polyhaven(query, asset_type=ph_type, limit=4)
        for hit in ph_hits:
            downloaded = await self._download_polyhaven_asset(hit["id"], ph_type, target_assets_dir)
            if downloaded:
                await _emit(f"[Poly Haven CC0] Downloaded '{hit['name']}' -> {downloaded.name}")
                updated.update(
                    {
                        "resolved_source": "polyhaven",
                        "local_path": str(downloaded),
                        "display_name": hit["name"],
                        "license": "CC0 (Poly Haven)",
                        "status": "resolved",
                    }
                )
                return updated

        # Tier 5: Hugging Face Free AI 3D Fallback (when enabled & unique hero prop)
        if allow_hf_fallback and category in ("prop", "anatomy"):
            await _emit(f"[HF AI 3D] Attempting free 3D mesh generation for '{query}'...")
            hf = await self.generate_hf_ai_3d(query, target_assets_dir)
            if hf:
                await _emit(f"[HF AI 3D] Generated '{hf['display_name']}'")
                updated.update(
                    {
                        "resolved_source": "huggingface",
                        "local_path": hf["local_path"],
                        "display_name": hf["display_name"],
                        "license": hf["license"],
                        "status": "resolved",
                    }
                )
                return updated

        # Tier 6: Procedural bpy fallback (always succeeds!)
        await _emit(f"[Procedural bpy] Using native procedural 3D builder for '{query}'")
        updated.update(
            {
                "resolved_source": "procedural",
                "local_path": None,
                "display_name": f"Procedural: {query}",
                "license": "Native bpy",
                "status": "procedural_fallback",
            }
        )
        return updated


def _infer_character_type(stem: str) -> str:
    if any(k in stem for k in ("female", "woman", "girl", "claire", "kate", "megan")):
        return "female"
    if any(k in stem for k in ("male", "man", "boy", "remy", "leonard", "adam")):
        return "male"
    if any(k in stem for k in ("doctor", "medic", "surgeon")):
        return "medical"
    return "stylized_human"
