import streamlit as st
import asyncio, aiohttp, pandas as pd, re, time, io
from bs4 import BeautifulSoup

# ================= UI CONFIG =================
st.set_page_config(page_title="MST Scraper Pro", layout="wide", page_icon="🚀")

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #d7e1ec, #f5f7fa) !important;
}
.header {
    background: linear-gradient(135deg, #1f4037, #99f2c8);
    padding: 18px;
    border-radius: 16px;
    text-align: center;
    color: white;
    font-weight: 800;
    font-size: 25px;
    margin-bottom: 20px;
}
.stButton>button {
    background: linear-gradient(135deg, #00c6ff, #0072ff);
    color: white;
    border-radius: 10px;
    width: 100%;
    height: 50px;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="header">HỆ THỐNG TRA CỨU VAI TRÒ DKKD</div>', unsafe_allow_html=True)

# ================= SAFE HELPERS =================
def get_value(soup, name):
    tag = soup.find("input", {"name": name})
    return tag["value"] if tag and tag.has_attr("value") else ""


# ================= GET PARAMS =================
async def get_params(session, url):
    try:
        async with session.get(url, ssl=True, timeout=15) as r:
            html = await r.text()
            soup = BeautifulSoup(html, "lxml")

            return {
                "v": get_value(soup, "__VIEWSTATE"),
                "n": get_value(soup, "ctl00$nonceKeyFld"),
                "h": get_value(soup, "ctl00$hdParameter"),
            }
    except:
        return None


# ================= SCRAPER =================
async def run_mst(session, mst, sem, p, url):
    async with sem:
        mst = str(mst).strip()
        mst_fmt = f"{mst[:10]}-{mst[10:]}" if len(mst) == 13 else mst

        payload = {
            "ctl00$SM": "ctl00$C$UpdatePanel1|ctl00$C$UC_PERS_LIST1$BtnFilter",
            "__VIEWSTATE": p.get("v", ""),
            "ctl00$nonceKeyFld": p.get("n", ""),
            "ctl00$hdParameter": p.get("h", ""),
            "ctl00$C$UC_PERS_LIST1$ENTERPRISE_CODEFilterFld": mst_fmt,
            "__ASYNCPOST": "true",
            "ctl00$C$UC_PERS_LIST1$BtnFilter": "Tìm kiếm"
        }

        for _ in range(3):  # retry mạnh hơn
            try:
                async with session.post(url, data=payload, ssl=True, timeout=25) as r:
                    text = await r.text()

                    # safe extract
                    match = re.search(
                        r'updatePanel\|ctl00_C_UpdatePanel1\|(.*?)\|hiddenField',
                        text, re.S
                    )

                    raw_html = match.group(1) if match else text
                    soup = BeautifulSoup(raw_html, "lxml")

                    table = soup.find("table", id=re.compile("UC_PERS_LIST1"))

                    if not table:
                        return [{
                            "MST": mst_fmt,
                            "Trạng thái": "Không có dữ liệu"
                        }]

                    headers = [th.get_text(strip=True) for th in table.find_all("th")]

                    rows = []
                    for tr in table.find_all("tr")[1:]:
                        tds = tr.find_all("td")
                        if not tds:
                            continue

                        row = {
                            "MST": mst_fmt,
                            "Trạng thái": "OK"
                        }

                        for h, td in zip(headers, tds):
                            if h:
                                row[h] = re.sub(r"\s+", " ", td.get_text(strip=True))

                        rows.append(row)

                    return rows

            except:
                await asyncio.sleep(1)

        return [{"MST": mst_fmt, "Trạng thái": "Lỗi request"}]


# ================= UI =================
with st.sidebar:
    st.header("Cấu hình")
    cookie_raw = st.text_area("Cookie", height=180)

    # FIX CLOUD SAFE CONCURRENCY
    concurrency = st.slider("Số luồng", 3, 20, 10)

    base_url = st.text_input("URL hệ thống")

uploaded_file = st.file_uploader("Upload MST (.txt / .xlsx)", type=["txt", "xlsx"])
btn = st.button("BẮT ĐẦU 🚀")


# ================= MAIN =================
if btn:

    if not (cookie_raw and base_url and uploaded_file):
        st.error("Thiếu dữ liệu đầu vào!")
        st.stop()

    # LOAD FILE
    if uploaded_file.name.endswith(".txt"):
        mst_list = [x.strip() for x in uploaded_file.read().decode().splitlines() if x.strip()]
    else:
        mst_list = pd.read_excel(uploaded_file, header=None)[0].dropna().astype(str).tolist()

    # COOKIE PARSE
    cookies = {}
    for c in cookie_raw.split(";"):
        if "=" in c:
            k, v = c.split("=", 1)
            cookies[k.strip()] = v.strip()

    prog = st.progress(0)
    stat = st.empty()
    metr = st.empty()

    async def main():
        connector = aiohttp.TCPConnector(limit=0, ssl=True)

        async with aiohttp.ClientSession(
            cookies=cookies,
            connector=connector,
            headers={
                "User-Agent": "Mozilla/5.0",
                "X-Requested-With": "XMLHttpRequest"
            }
        ) as session:

            p = await get_params(session, base_url)
            if not p:
                return [{"Lỗi": "Không lấy được VIEWSTATE"}]

            sem = asyncio.Semaphore(concurrency)

            tasks = [
                run_mst(session, m, sem, p, base_url)
                for m in mst_list
            ]

            results = []
            start = time.time()

            for i, coro in enumerate(asyncio.as_completed(tasks), 1):
                res = await coro
                results.extend(res)

                elapsed = time.time() - start
                speed = i / elapsed if elapsed else 0

                prog.progress(i / len(mst_list))
                stat.text(f"Đang xử lý: {i}/{len(mst_list)}")

                metr.markdown(
                    f"⚡ {speed:.2f} req/s | ⏳ còn ~{int((len(mst_list)-i)/speed) if speed else 0}s"
                )

            return results


    # ================= FIX STREAMLIT CLOUD ASYNC =================
    import nest_asyncio
    nest_asyncio.apply()

    loop = asyncio.get_event_loop()
    data = loop.run_until_complete(main())

    # ================= OUTPUT =================
    df = pd.DataFrame(data)
    df = df.dropna(axis=1, how="all")

    st.success(f"Hoàn thành {len(mst_list)} MST")
    st.dataframe(df, use_container_width=True)

    # EXPORT
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    st.download_button(
        "📥 Tải Excel",
        output.getvalue(),
        file_name=f"ketqua_{int(time.time())}.xlsx",
        mime="application/vnd.ms-excel"
    )
