import streamlit as st
import asyncio, aiohttp, pandas as pd, re, time, io
from bs4 import BeautifulSoup

# --- UI CONFIG & STYLE ---
st.set_page_config(page_title="MST Scraper Pro", layout="wide", page_icon="🚀")

st.markdown("""<style>
    .stApp { background: linear-gradient(135deg, #d7e1ec, #f5f7fa); }
    .header-container {
        display: flex;
        align-items: center;
        background: linear-gradient(135deg, #1f4037, #99f2c8);
        padding: 15px;
        border-radius: 16px;
        margin-bottom: 20px;
        color: white;
    }
    .logo-img {
        border-radius: 10px;
        margin-right: 20px;
    }
    .header-text {
        flex-grow: 1;
        text-align: center;
        font-weight: 800;
        font-size: 25px;
        margin: 0;
    }
    .stButton>button { 
        background: linear-gradient(135deg, #00c6ff, #0072ff); 
        color: white; 
        border-radius: 10px; 
        width: 100%; 
        height: 50px; 
        font-weight: bold; 
    }
</style>""", unsafe_allow_html=True)

# --- HEADER WITH LOGO ---
col_logo, col_title = st.columns([1, 6])

with col_logo:
    # Hiển thị logo từ file đã upload
    try:
        st.image("logo.jpg", width=100)
    except:
        st.error("Thiếu file logo.jpg")

with col_title:
    st.markdown('<div class="header-container"><p class="header-text">HỆ THỐNG TRA CỨU VAI TRÒ CÁ NHÂN DKKD</p></div>', unsafe_allow_html=True)

# --- BACKEND LOGIC ---
async def get_params(session, url):
    try:
        async with session.get(url, ssl=False, timeout=10) as r:
            soup = BeautifulSoup(await r.text(), "lxml")
            return {
                k: soup.find("input", {"name": v})
                for k, v in {
                    "n": "ctl00$nonceKeyFld",
                    "h": "ctl00$hdParameter",
                    "v": "__VIEWSTATE"
                }.items()
            }
    except:
        return None

async def run_mst(session, mst, sem, p, url):
    async with sem:
        mst_fmt = f"{mst[:10]}-{mst[10:]}" if len(str(mst)) == 13 else str(mst)

        payload = {
            "ctl00$SM": "ctl00$C$UpdatePanel1|ctl00$C$UC_PERS_LIST1$BtnFilter",
            "__VIEWSTATE": p['v']["value"] if p.get('v') else "",
            "ctl00$nonceKeyFld": p['n']["value"] if p.get('n') else "",
            "ctl00$hdParameter": p['h']["value"] if p.get('h') else "",
            "ctl00$C$UC_PERS_LIST1$ENTERPRISE_CODEFilterFld": mst_fmt,
            "__ASYNCPOST": "true",
            "ctl00$C$UC_PERS_LIST1$BtnFilter": "Tìm kiếm"
        }

        for _ in range(2):
            try:
                async with session.post(url, data=payload, ssl=False, timeout=20) as r:
                    text = await r.text()
                    match = re.search(r'updatePanel\|ctl00_C_UpdatePanel1\|(.*?)\|hiddenField', text, re.S)
                    soup = BeautifulSoup(match.group(1) if match else text, "lxml")
                    table = soup.find("table", id=re.compile("UC_PERS_LIST1"))

                    if not table:
                        return [{"MST_Gốc": mst_fmt, "Trạng_Thái": "Không có dữ liệu"}]

                    hdrs = [th.get_text(strip=True) for th in table.find_all("th")]

                    return [
                        {
                            "MST_Gốc": mst_fmt,
                            "Trạng_Thái": "Thành công",
                            **{
                                h: re.sub(r"\s+", " ", td.get_text(strip=True))
                                for h, td in zip(hdrs, tr.find_all("td"))
                                if h and td.get_text(strip=True)
                            }
                        }
                        for tr in table.find_all("tr")[1:]
                        if tr.find_all("td")
                    ]
            except:
                await asyncio.sleep(0.5)

        return [{"MST_Gốc": mst_fmt, "Trạng_Thái": "Lỗi kết nối"}]

# --- UI INPUTS ---
with st.sidebar:
    st.header("Cấu hình")
    cookie_raw = st.text_area("Dán Cookie", height=200)
    concurrency = st.slider("Số luồng (Concurrency)", 5, 100, 25)
    base_url = st.text_input("URL hệ thống (Bắt buộc)")

uploaded_file = st.file_uploader("Upload danh sách MST (txt hoặc xlsx)", type=["txt", "xlsx"])
btn_start = st.button("BẮT ĐẦU 🚀")

# --- MAIN PROCESS ---
if btn_start:
    if not (base_url and cookie_raw and uploaded_file):
        st.error("Vui lòng điền đầy đủ URL, Cookie và Upload file!")
    else:
        # Load MST List
        if uploaded_file.name.endswith(".txt"):
            mst_list = [l.decode().strip() for l in uploaded_file if l.strip()]
        else:
            mst_list = pd.read_excel(uploaded_file, header=None)[0].dropna().astype(str).tolist()

        cookies = {
            c.split("=")[0].strip(): c.split("=")[1].strip()
            for c in cookie_raw.split(";")
            if "=" in c
        }

        prog, stat, metr = st.progress(0), st.empty(), st.empty()

        async def main():
            conn = aiohttp.TCPConnector(limit=0, ssl=False)
            async with aiohttp.ClientSession(
                cookies=cookies,
                connector=conn,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "X-Requested-With": "XMLHttpRequest"
                }
            ) as sess:
                p = await get_params(sess, base_url)
                if not p:
                    return [{"Lỗi": "Không thể kết nối hoặc URL sai"}]

                sem = asyncio.Semaphore(concurrency)
                results, start, total = [], time.time(), len(mst_list)
                tasks = [run_mst(sess, m, sem, p, base_url) for m in mst_list]

                for i, coro in enumerate(asyncio.as_completed(tasks), 1):
                    res = await coro
                    results.extend(res)
                    elapsed = time.time() - start
                    speed = i / elapsed if elapsed > 0 else 0
                    prog.progress(i / total)
                    metr.markdown(f"⚡ **Tốc độ:** {speed:.2f} req/s | ⏳ **Dự kiến còn:** {int((total-i)/speed) if speed > 0 else 0}s")
                    stat.text(f"Đang xử lý: {i}/{total}")
                return results

        data = asyncio.run(main())

        df = pd.DataFrame(data)
        df = df.dropna(axis=1, how='all')
        df = df.loc[:, ~(df.astype(str).apply(lambda col: col.str.strip().eq('').all()))]

        st.success(f"Hoàn thành tra cứu {len(mst_list)} MST!")
        st.dataframe(df, use_container_width=True)

        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)

        st.download_button(
            "📥 Tải kết quả Excel",
            out.getvalue(),
            f"ketqua_{int(time.time())}.xlsx",
            mime="application/vnd.ms-excel"
        )