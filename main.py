import os
import uvicorn
from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests
from io import BytesIO
from fastapi.responses import StreamingResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "API Selic com upload de Excel - Atualização automática"}

@app.post("/upload_excel/")
async def upload_excel(file: UploadFile):
    try:
        df = pd.read_excel(file.file)
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json"
        data = requests.get(url, timeout=10).json()
        selic = pd.DataFrame(data)
        selic['data'] = pd.to_datetime(selic['data'], format='%d/%m/%Y')
        selic['valor'] = selic['valor'].str.replace(',', '.').astype(float)
        if 'Data' not in df.columns or 'Valor Inicial' not in df.columns:
            return {"error": "O arquivo Excel deve conter as colunas: Data e Valor Inicial"}
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True)
        df_merged = df.merge(selic, left_on=df['Data'].dt.to_period('M'),
                             right_on=selic['data'].dt.to_period('M'), how='left')
        df_merged = df_merged.rename(columns={'valor': 'Taxa Selic (%)'})
        df_merged['Valor Atualizado'] = df_merged['Valor Inicial'] * (1 + df_merged['Taxa Selic (%)'] / 100)
        output = BytesIO()
        df_merged[['Data', 'Valor Inicial', 'Taxa Selic (%)', 'Valor Atualizado']].to_excel(output, index=False)
        output.seek(0)
        return StreamingResponse(output, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                 headers={"Content-Disposition": "attachment; filename=result_selic.xlsx"})
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
