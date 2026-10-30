import streamlit as st
import pandas as pd
import plotly.express as px
from ortools.sat.python import cp_model

# Sayfa Yapılandırması
st.set_page_config(page_title="ANSA Ambalaj - Çizelgeleme Karar Destek Sistemi", layout="wide")

st.title("🏭 ANSA Ambalaj - Üretim Çizelgeleme & Optimizasyon Paneli")
st.markdown("**Endüstri Mühendisliği Bitirme Tezi - Karar Destek Sistemi**")

# Yan Panel - Dosya Yükleme ve Parametreler
st.sidebar.header("📁 Veri ve Parametre Girişi")
uploaded_file = st.sidebar.file_uploader("Excel Veri Dosyasını Yükleyin", type=["xlsx"])

if uploaded_file is not None:
    # Verileri Okuma
    df_orders = pd.read_excel(uploaded_file, sheet_name='İş Emirleri (Siparişler)')
    df_setup = pd.read_excel(uploaded_file, sheet_name='Hazırlık Süreleri (Setup)')
    
    st.success(f"Veri Başarıyla Yüklendi! Toplam **{len(df_orders)}** iş emri işlenmeye hazır.")
    
    if st.sidebar.button("🚀 Optimizasyon Modelini Çalıştır"):
        with st.spinner("CP-SAT Çözücü çalışıyor, lütfen bekleyin..."):
            
            # --- MODEL KURULUMU ---
            model = cp_model.CpModel()
            is_sayisi = len(df_orders)
            ufuk_suresi = int(df_orders['Tahmini İşlem Süresi (Saat)'].sum() * 2) + 500
            
            is_araliklari = {}
            makine_isleri = {}
            gecikme_degiskenleri = []
            
            df_orders['Hedef Teslim Tarihi'] = pd.to_datetime(df_orders['Hedef Teslim Tarihi'], format='%d.%m.%Y', errors='coerce')
            min_tarih = df_orders['Hedef Teslim Tarihi'].min()
            
            for i in range(is_sayisi):
                is_kodu = df_orders.loc[i, 'Sipariş / İş Kodu (Müşteri gizli)']
                
                # --- GERÇEK SÜRE OKUMA (Miktar/50 İPTAL EDİLDİ) ---
                is_suresi = max(1, int(df_orders.loc[i, 'Tahmini İşlem Süresi (Saat)']))
                
                makine = df_orders.loc[i, 'Makine']
                tarih_val = df_orders.loc[i, 'Hedef Teslim Tarihi']
                
                if pd.notnull(tarih_val) and pd.notnull(min_tarih):
                    gun_farki = (tarih_val - min_tarih).days
                    hedef_teslim = max(10, gun_farki * 24)
                else:
                    hedef_teslim = 1000 + (i * 20)
                
                baslangic = model.NewIntVar(0, ufuk_suresi, f'baslangic_{i}')
                bitis = model.NewIntVar(0, ufuk_suresi, f'bitis_{i}')
                aralik = model.NewIntervalVar(baslangic, is_suresi, bitis, f'aralik_{i}')
                
                gecikme = model.NewIntVar(0, ufuk_suresi, f'gecikme_{i}')
                model.AddMaxEquality(gecikme, [0, bitis - hedef_teslim])
                gecikme_degiskenleri.append(gecikme)
                
                is_araliklari[i] = {
                    'baslangic': baslangic,
                    'bitis': bitis,
                    'aralik': aralik,
                    'makine': makine,
                    'gecikme': gecikme,
                    'is_kodu': is_kodu
                }
                
                if makine not in makine_isleri:
                    makine_isleri[makine] = []
                makine_isleri[makine].append(i)
            
            # Çakışmasızlık Kısıtı
            for makine, iş_indeksleri in makine_isleri.items():
                if len(iş_indeksleri) > 1:
                    aralik_listesi = [is_araliklari[i]['aralik'] for i in iş_indeksleri]
                    model.AddNoOverlap(aralik_listesi)
            
            # Amaç Fonksiyonu
            toplam_gecikme = model.NewIntVar(0, 1000000, 'toplam_gecikme')
            model.Add(toplam_gecikme == sum(gecikme_degiskenleri))
            
            tum_bitisler = [is_araliklari[i]['bitis'] for i in range(is_sayisi)]
            maksimum_bitis = model.NewIntVar(0, ufuk_suresi, 'maksimum_bitis')
            model.AddMaxEquality(maksimum_bitis, tum_bitisler)
            model.Minimize(maksimum_bitis + (5 * toplam_gecikme))
            
            # Çözücü
            solver = cp_model.CpSolver()
            status = solver.Solve(model)
            
            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                st.balloons()
                st.header("📊 Optimizasyon Sonuçları ve KPI'lar")
                
                makespan_val = int(solver.Value(maksimum_bitis))
                tardiness_val = int(solver.Value(toplam_gecikme))
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Toplam Tamamlama (Makespan)", f"{makespan_val} Saat")
                col2.metric("Toplam Gecikme Ceza Puanı", f"{tardiness_val}")
                col3.metric("Planlanan İş Sayısı", f"{is_sayisi} Adet")
                
                gantt_list = []
                for i in range(is_sayisi):
                    baslangic_val = int(solver.Value(is_araliklari[i]['baslangic']))
                    bitis_val = int(solver.Value(is_araliklari[i]['bitis']))
                    sure_val = bitis_val - baslangic_val
                    
                    gantt_list.append({
                        'İş Kodu': str(is_araliklari[i]['is_kodu']),
                        'Makine': str(is_araliklari[i]['makine']),
                        'Başlangıç': baslangic_val,
                        'Bitiş': bitis_val,
                        'Süre': sure_val
                    })
                
                df_gantt = pd.DataFrame(gantt_list)
                
                st.subheader("📅 Üretim Gantt Şeması (Makine Bazlı Çizelge)")
                
                fig = px.bar(
                    df_gantt, 
                    x='Süre', 
                    y='Makine', 
                    base='Başlangıç',
                    color='İş Kodu',
                    orientation='h',
                    custom_data=['İş Kodu', 'Başlangıç', 'Bitiş', 'Süre'],
                    title="<b>Makine Çizelgeleme Çıktısı (İnteraktif Gantt)</b>"
                )
                
                fig.update_traces(
                    marker_line_color='black',
                    marker_line_width=1.0,
                    opacity=0.9,
                    hovertemplate=(
                        "<span style='font-size:14px; font-weight:bold;'>📦 İş Detayları</span><br>"
                        "<b>İş Kodu:</b> %{customdata[0]}<br>"
                        "<b>Makine:</b> %{y}<br>"
                        "<b>Başlangıç Zamanı:</b> %{customdata[1]} Saat<br>"
                        "<b>Bitiş Zamanı:</b> %{customdata[2]} Saat<br>"
                        "<b>İşlem Süresi:</b> %{customdata[3]} Saat<br>"
                        "<extra></extra>"
                    )
                )
                
                fig.update_layout(
                    height=650,
                    bargap=0.2,
                    xaxis=dict(title="Zaman (Saat)", range=[0, max(5000, makespan_val + 200)], autorange=False, showgrid=True),
                    yaxis=dict(title="Makine", autorange="reversed", showgrid=True),
                    hoverlabel=dict(bgcolor="white", font_size=13, font_family="Arial", font_color="black", bordercolor="#333")
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("📋 Detaylı Çizelge Tablosu")
                st.dataframe(df_gantt, use_container_width=True)
            else:
                st.error("Model için geçerli bir çözüm bulunamadı!")
else:
    st.info("Lütfen sol taraftaki panelden Excel dosyanızı yükleyin.")
