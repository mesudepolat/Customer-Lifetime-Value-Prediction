##############################################################
# BG-NBD ve Gamma-Gamma ile CLTV Prediction
##############################################################

# 1.Data Preperation
# 2.BG/NBD ile Expected Sale Forecasting değerlerini hesapla
# 3.Gamma-Gamma ile Expected Average Profit değerlerini hesapla
# 4.BG/NBD ve Gamma Gamma modeli ile CLTV hesapla


##############################################################
# 1. Data Preperation
##############################################################

import datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
from lifetimes import BetaGeoFitter
from lifetimes import GammaGammaFitter
from lifetimes.plotting import plot_period_transactions

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', 10)
pd.set_option('display.float_format', lambda x: '%.5f' % x)

def outlier_thresholds(dataframe, variable):
    quartile1 = dataframe[variable].quantile(0.01)
    quartile3 = dataframe[variable].quantile(0.99)
    interquantile_range = quartile3 - quartile1
    up_limit = quartile3 + 1.5 * interquantile_range
    low_limit = quartile1 - 1.5 * interquantile_range
    return low_limit, up_limit


def replace_with_thresholds(dataframe, variable):
    low_limit, up_limit = outlier_thresholds(dataframe, variable)
    # dataframe.loc[(dataframe[variable] < low_limit), variable] = low_limit
    dataframe.loc[(dataframe[variable] > up_limit), variable] = up_limit

df_ =pd.read_excel("datasets/online_retail_II.xlsx",
                   sheet_name="Year 2010-2011")
df = df_.copy()

df.shape # (541910, 8)
df.head()
df.tail()
df.info()
df.describe([0.05, 0.25, 0.50, 0.75, 0.95, 0.99]).T

df.dropna(inplace=True)
df = df[~df["Invoice"].str.contains("C", na=False)]
df = df[df["Quantity"] > 0]

replace_with_thresholds(df, "Quantity")
replace_with_thresholds(df, "Price")
df.describe([0.05, 0.25, 0.50, 0.75, 0.95, 0.99, 1]).T

df["TotalPrice"] = df["Price"] * df["Quantity"]

df["InvoiceDate"].max()
today_date = dt.datetime(2011, 12, 11)

# UK müşterilerini seçme
df = df[df["Country"] == "United Kingdom"]
# df = df[df["Country"].str.contains("United Kingdom")]

df.head()
#############################################
# RFM Table
#############################################
# metrikleri oluşturma
rfm = df.groupby('Customer ID').agg({'InvoiceDate': [lambda date: (date.max()-date.min()).days,
                                                     lambda date: (today_date-date.min()).days],
                                     'Invoice': lambda num: num.nunique(),
                                     'TotalPrice': lambda price: price.sum()})
rfm.columns = rfm.columns.droplevel(0)

# sütunları isimlendirme
rfm.columns = ['recency_cltv_p', 'tenure', 'frequency', 'monetary']

# monetary avg hesaplama --> Gamma Gamma modeli bu şekilde istiyor
rfm["monetary"] = rfm["monetary"] / rfm["frequency"]

rfm.rename(columns={"monetary": "monetary_avg"}, inplace=True)

# recency ve tenure değişkenlerini haftalığa çevirme
rfm["recency_weekly_p"] = rfm["recency_cltv_p"] / 7
rfm["tenure_weekly_p"] = rfm["tenure"] / 7

# kontroller
rfm = rfm[rfm["monetary_avg"] > 0]
rfm = rfm[rfm["frequency"] > 1]
rfm["frequency"] = rfm["frequency"].astype(int)



##############################################################
# 2. BG/NBD modelinin kurulması
##############################################################
bgf = BetaGeoFitter(penalizer_coef=0.001)
bgf.fit(rfm['frequency'],
        rfm['recency_weekly_p'],
        rfm['tenure_weekly_p'])


# 6 ay içinde en çok satın alma beklediğimiz 10 müşteri kimdir?
bgf.conditional_expected_number_of_purchases_up_to_time(24,
                                                        rfm['frequency'],
                                                        rfm['recency_weekly_p'],
                                                        rfm['tenure_weekly_p']).sort_values(ascending=False).head(10)

rfm["exp_sales_6_month"] = bgf.predict(24,
                                        rfm['frequency'],
                                        rfm['recency_weekly_p'],
                                        rfm['tenure_weekly_p'])

rfm.sort_values("exp_sales_6_month", ascending=False).head(20)


# 6 Ayda Tüm Şirketin Beklenen Satış Sayısı Nedir?  952.4548865072431
bgf.predict(4*6,
            rfm['frequency'],
            rfm['recency_weekly_p'],
            rfm['tenure_weekly_p']).sum()


# Tahmin Sonuçlarının Değerlendirilmesi
plot_period_transactions(bgf)
plt.show()

##############################################################
# 3. GAMMA-GAMMA modelinin kurulması
##############################################################
ggf = GammaGammaFitter(penalizer_coef=0.01)
ggf.fit(rfm['frequency'], rfm['monetary_avg'])

ggf.conditional_expected_average_profit(rfm['frequency'],
                                        rfm['monetary_avg']).sort_values(ascending=False).head(10)

rfm["expected_average_profit"] = ggf.conditional_expected_average_profit(rfm['frequency'],
                                                                         rfm['monetary_avg'])
rfm.sort_values("expected_average_profit", ascending=False).head(20)


# geçmiş ayların ortalama satış sayılarını bulma?



##############################################################
# 4. BG-NBD ve GG modeli ile CLTV'nin hesaplanması.
##############################################################
# GÖREV - 1
# 2010-2011 UK müşterileri için 6 aylık CLTV prediction
cltv = ggf.customer_lifetime_value(bgf,
                                   rfm['frequency'],
                                   rfm['recency_weekly_p'],
                                   rfm['tenure_weekly_p'],
                                   rfm['monetary_avg'],
                                   time=6,
                                   freq="W",
                                   discount_rate=0.01)
cltv.head()
cltv.shape
cltv = cltv.reset_index()
cltv.sort_values(by="clv", ascending=False).head(50)
rfm_cltv_final = rfm.merge(cltv, on="Customer ID", how="left")
rfm_cltv_final.sort_values(by="clv", ascending=False).head(7)

rfm_cltv_final[rfm_cltv_final["Customer ID"] == 12748.00000]
# GÖREV - 2
# 2010-2011 UK müşterileri için 1 aylık ve 12 aylık CLTV prediction
# - 1 aylık CLTV'de en yüksek olan 10 kişi ile 12 aylık'taki en yüksek 10 kişiyi analiz ediniz.
# - Fark var mı? Varsa sizce neden olabilir?

# 1 aylık
cltv = ggf.customer_lifetime_value(bgf,
                                   rfm['frequency'],
                                   rfm['recency_weekly_p'],
                                   rfm['tenure_weekly_p'],
                                   rfm['monetary_avg'],
                                   time=1, # 1ay
                                   freq="W",
                                   discount_rate=0.01)
# 1 aylık CLTV'de en yüksek olan 10 kişi
cltv.head(10)
cltv.shape
cltv = cltv.reset_index()
cltv.sort_values(by="clv", ascending=False).head(50)
rfm_cltv_final = rfm.merge(cltv, on="Customer ID", how="left")
rfm_cltv_final.sort_values(by="clv", ascending=False).head()

# 12 aylık
cltv = ggf.customer_lifetime_value(bgf,
                                   rfm['frequency'],
                                   rfm['recency_weekly_p'],
                                   rfm['tenure_weekly_p'],
                                   rfm['monetary_avg'],
                                   time=12, # 12ay
                                   freq="W",
                                   discount_rate=0.01)
# 12 aylık CLTV'de en yüksek olan 10 kişi
cltv.head(10)
cltv.shape
cltv = cltv.reset_index()
cltv.sort_values(by="clv", ascending=False).head(50)
rfm_cltv_final = rfm.merge(cltv, on="Customer ID", how="left")
rfm_cltv_final.sort_values(by="clv", ascending=False).head()

# GÖREV - 3
# 2010-2011 UK müşterileri için 6 aylık CLTV'ye göre tüm müşterilerinizi 3 gruba (segmente) ayırınız ve
# grup isimlerini veri setine ekleyiniz. Örneğin (C, B, A)
# CLTV'ye göre en iyi yüzde 20'yi seçiniz. Ve bunlara top_flag yazınız. yüzde 20'ye 1.
# diğerlerine 0 yazınız.
# 3 grubu veri setindeki diğer değişkenler açısıdan analiz ediniz.
# 3 grup için yönetime 6 aylık aksiyon önerilerinde bulununuz. Kısa kısa.

cltv = ggf.customer_lifetime_value(bgf,
                                   rfm['frequency'],
                                   rfm['recency_weekly_p'],
                                   rfm['tenure_weekly_p'],
                                   rfm['monetary_avg'],
                                   time=6,
                                   freq="W",
                                   discount_rate=0.01)
cltv.head()
rfm_cltv_final = rfm.merge(cltv, on="Customer ID", how="left")
rfm_cltv_final["Segment"] = pd.qcut(rfm_cltv_final["clv"], 3, labels=["C", "B", "A"])
rfm_cltv_final.sort_values(by="clv", ascending=False).head(10)

cltv["clv"]


pareto = rfm_cltv_final.sort_values(by="clv", ascending=False)
pareto["clv"].shape[0] # 2570
pareto["clv"].shape[0] * 0.20 # 514.0
pareto["top_flag"] = pareto["clv"].shape[0]
pareto["top_flag"] = 0
pareto["top_flag"].iloc[0:514] = 1

rfm_cltv_final.groupby("Segment").agg({"sum", "count", "max"})




