# 智能彩券選號系統 Pro - 專案文檔

## 📋 專案概述

**專案名稱**：智能彩券選號系統 Pro  
**目標市場**：台灣樂透玩家  
**當前狀態**：Web Prototype（完整功能版）  
**技術棧**：純前端 HTML + CSS + JavaScript（無依賴）  
**文件位置**：`/mnt/user-data/outputs/lotto-pro.html`

---

## 🎯 核心價值主張

1. **智能選號演算法**：避免連號、奇偶平衡、自選必含號碼
2. **冷熱號統計**：基於歷史數據的頻率分析
3. **雙模式支援**：大樂透 (6/49) + 威力彩 (6/38+1/8)
4. **個人化收藏**：LocalStorage永久儲存喜愛組合
5. **一鍵複製**：方便快速投注

---

## ✅ 已實現功能列表

### 1. 核心選號功能
- [x] 大樂透模式：6個號碼 (1-49) + 1個特別號
- [x] 威力彩模式：6個號碼 (1-38) + 1個第二區號碼 (1-8)
- [x] 一鍵生成5組號碼
- [x] 排除連號選項（可開關）
- [x] 奇偶平衡選項（2-4個奇數，可開關）
- [x] 自選必含號碼（最多3個）

### 2. 數據分析功能
- [x] 冷熱號統計（基於最近5期開獎）
- [x] TOP 5 熱門號碼條形圖
- [x] TOP 5 冷門號碼條形圖
- [x] 號碼球上的🔥❄️視覺標記
- [x] 歷史開獎記錄顯示（最近5期）

### 3. 用戶體驗功能
- [x] 統計儀表板（已生成組數、收藏組數、當前模式）
- [x] 每組號碼的「複製」按鈕
- [x] 每組號碼的「收藏」按鈕
- [x] 收藏管理（查看、刪除）
- [x] LocalStorage持久化儲存
- [x] Toast提示訊息
- [x] 響應式設計（手機可用）

### 4. UI/UX設計
- [x] 漸層紫色主題
- [x] 卡片式佈局
- [x] 圓形號碼球設計
- [x] Toggle開關動畫
- [x] 按鈕Hover效果
- [x] 模式切換按鈕

---

## 🏗️ 技術架構

### 前端架構
```
純 Vanilla JavaScript
├── 無外部依賴
├── 單一HTML檔案（Self-contained）
└── 約 700 行代碼（HTML+CSS+JS）
```

### 數據結構
```javascript
// 歷史開獎記錄
lottoHistory = [
  { date: '2024/12/27', numbers: [3,15,23,28,35,42], special: 18 }
]

// 收藏號碼
savedNumbers = [
  { 
    id: 1234567890, 
    mode: 'lotto', 
    numbers: [1,2,3,4,5,6], 
    special: 7,
    date: '2024/12/27' 
  }
]

// 必含號碼
mustHaveNumbers = [7, 13, 21]
```

### 核心演算法

#### 1. 號碼生成邏輯
```javascript
function generateSingleSet(maxNum) {
  // 從必含號碼開始
  const numbers = [...mustHaveNumbers];
  
  // 補足到6個號碼
  while (numbers.length < 6) {
    const num = Math.floor(Math.random() * maxNum) + 1;
    if (!numbers.includes(num)) {
      numbers.push(num);
    }
  }
  
  return numbers.sort((a, b) => a - b);
}
```

#### 2. 連號檢測
```javascript
function hasConsecutive(numbers) {
  for (let i = 0; i < numbers.length - 1; i++) {
    if (numbers[i + 1] - numbers[i] === 1) {
      return true;
    }
  }
  return false;
}
```

#### 3. 奇偶平衡檢測
```javascript
function isBalanced(numbers) {
  const oddCount = numbers.filter(n => n % 2 === 1).length;
  return oddCount >= 2 && oddCount <= 4; // 允許2,3,4個奇數
}
```

#### 4. 冷熱號計算
```javascript
function calculateHotColdNumbers() {
  const frequency = {};
  
  // 統計每個號碼出現次數
  history.forEach(record => {
    record.numbers.forEach(num => {
      frequency[num] = (frequency[num] || 0) + 1;
    });
  });
  
  // 排序找出TOP 5
  const sorted = Object.entries(frequency).sort((a, b) => b[1] - a[1]);
  const hot = sorted.slice(0, 5);
  const cold = sorted.slice(-5).reverse();
  
  return { hot, cold, frequency };
}
```

---

## 🔧 當前限制與待優化項目

### 1. 數據源限制
- ❌ **問題**：歷史開獎資料是硬編碼（只有5期）
- ✅ **優化方向**：串接台彩官網API或爬蟲自動更新

### 2. 演算法可改進
- ❌ **問題**：隨機生成後過濾，效率較低
- ✅ **優化方向**：使用加權隨機（依冷熱號調整機率）

### 3. 統計分析深度
- ❌ **問題**：只有簡單頻率統計
- ✅ **優化方向**：
  - 號碼組合頻率（哪些號碼常一起出現）
  - 和值分析（總和落在哪個區間）
  - 區間分佈（1-10, 11-20...各幾個）
  - 遺漏期數分析

### 4. UI/UX細節
- ❌ **問題**：缺少載入動畫
- ✅ **優化方向**：號碼滾動動畫、生成動畫效果

### 5. 行動裝置優化
- ❌ **問題**：雖然是響應式，但未針對手機優化
- ✅ **優化方向**：更大的按鈕、更好的觸控體驗

---

## 🚀 未來功能規劃（優先順序排序）

### Phase 1: 差異化功能（核心競爭力）
1. **新聞數字功能** ⭐⭐⭐⭐⭐
   - 爬取PTT、Google News熱門數字
   - 例如：「台積電780元」→ 提取 7,8,0 → 轉換為樂透號碼
   - 這是競品都沒有的獨特功能

2. **AI智能推薦** ⭐⭐⭐⭐
   - 使用Claude API分析用戶偏好
   - 根據歷史選號習慣推薦

### Phase 2: 數據升級
3. **真實歷史數據API** ⭐⭐⭐⭐⭐
   - 串接台彩官網：https://www.taiwanlottery.com.tw
   - 或自建爬蟲定期更新
   - 儲存至少1年歷史數據

4. **進階統計分析** ⭐⭐⭐
   - 號碼組合熱力圖
   - 遺漏期數追蹤
   - 和值區間分析
   - 區域分布圖表

### Phase 3: 社交與分享
5. **社群分享功能** ⭐⭐⭐
   - 生成精美圖片（號碼組合卡片）
   - 分享到LINE、Facebook
   - QR Code快速分享

6. **用戶留言板** ⭐⭐
   - 讓中獎用戶分享心得
   - 建立社群氛圍

### Phase 4: 商業化功能
7. **訂閱制/解鎖功能** ⭐⭐⭐⭐
   - 免費版：基礎隨機選號
   - 付費版：解鎖所有演算法、無限生成、新聞數字

8. **廣告整合** ⭐⭐⭐
   - Google AdMob
   - 適合台灣市場的廣告平台

### Phase 5: App化
9. **React Native App** ⭐⭐⭐⭐
   - 使用現有HTML作為WebView基礎
   - 或完全重寫為原生體驗

10. **推播通知** ⭐⭐⭐
    - 開獎提醒
    - 大獎頭條通知

---

## 📂 專案文件結構（當前）

```
lotto-pro.html
├── <head>
│   ├── <meta> 標籤
│   └── <style> 約300行CSS
├── <body>
│   ├── Header（標題、模式切換）
│   ├── 統計儀表板卡片
│   ├── 選號設定卡片
│   │   ├── 必含號碼網格
│   │   ├── 選項開關
│   │   └── 生成按鈕
│   ├── 收藏號碼卡片
│   ├── 歷史開獎卡片
│   └── Footer
└── <script> 約400行JavaScript
    ├── 全局變數
    ├── 歷史數據（模擬）
    ├── 核心函數
    │   ├── calculateHotColdNumbers()
    │   ├── generateNumbers()
    │   ├── generateSingleSet()
    │   ├── hasConsecutive()
    │   ├── isBalanced()
    │   └── displayNumberSet()
    └── UI更新函數
        ├── updateCharts()
        ├── updateHistoryDisplay()
        ├── updateSavedDisplay()
        └── showToast()
```

---

## 🎨 設計規範

### 色彩系統
```css
主色調：#667eea → #764ba2（紫色漸層）
次要色：#e74c3c（紅色，特別號）
成功色：#27ae60（綠色）
資訊色：#3498db（藍色，冷門號）
警告色：#e74c3c（紅色，熱門號）
背景：#f7f7f7（淺灰）
文字：#333（深灰）
```

### 字體
```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft JhengHei", sans-serif
```

### 圓角與間距
```css
大圓角：20px（卡片）
中圓角：10-15px（按鈕）
小圓角：5-8px
間距單位：5px倍數（5, 10, 15, 20, 25...）
```

---

## 🐛 已知Bug與Edge Cases

### 1. 必含號碼衝突
- **情境**：選了3個必含號碼，但開啟「不連號」，可能無法生成
- **當前處理**：最多嘗試200次，失敗則可能包含連號
- **建議優化**：提前驗證設定是否衝突，給予警告

### 2. LocalStorage容量
- **情境**：收藏太多組合可能超過5MB限制
- **當前處理**：無限制
- **建議優化**：限制最多收藏50組

### 3. 模式切換後必含號碼未清空
- **情境**：大樂透選了必含號碼45-49，切到威力彩（只到38）會出錯
- **當前處理**：已在switchMode()清空mustHaveNumbers
- **狀態**：✅ 已修復

---

## 📝 給Claude Code的優化建議

### 優先度A（立即可做）
1. **程式碼重構**
   - 將CSS、JS分離成獨立檔案
   - 拆分functions成模組
   - 加入JSDoc註解

2. **錯誤處理**
   - try-catch包裹localStorage操作
   - 網路請求的錯誤處理（未來API用）

3. **效能優化**
   - 減少DOM操作次數
   - 使用DocumentFragment批量插入
   - 事件委派（Event Delegation）

### 優先度B（需要討論）
1. **TypeScript轉換**
   - 增加型別安全
   - 更好的IDE支援

2. **建置工具整合**
   - Webpack/Vite打包
   - 程式碼壓縮

3. **測試框架**
   - Jest單元測試
   - 覆蓋核心演算法

---

## 🔗 相關資源

### 官方資料來源
- 台灣彩券官網：https://www.taiwanlottery.com.tw
- 大樂透開獎API（需自行實作爬蟲）
- 威力彩開獎API（需自行實作爬蟲）

### 潛在整合服務
- Google AdMob（廣告）
- Stripe/綠界科技（金流）
- Firebase（資料庫+推播）
- Cloudflare Pages（免費hosting）

---

## 📊 預期成效

### 技術指標
- 首次載入：< 1秒
- 生成5組號碼：< 100ms
- 記憶體佔用：< 10MB
- 支援瀏覽器：Chrome 90+, Safari 14+, Firefox 88+

### 商業指標（預估）
- 目標用戶：台灣樂透玩家（約200萬活躍玩家）
- 預期DAU：500-1000（初期）
- 轉換率：5%（免費→付費）
- ARPU：NT$50/月

---

## 🚦 當前開發狀態

```
[████████░░] 80% 完成

✅ 核心功能
✅ UI/UX設計
✅ 雙模式支援
✅ 冷熱號分析
✅ 收藏系統
⬜ 真實數據API
⬜ 新聞數字功能
⬜ 部署上線
⬜ App化
⬜ 商業化
```

---

## 💡 下一步行動建議

**給Claude Code的任務清單：**

1. **立即優化**（1小時內）
   - [ ] 程式碼重構與模組化
   - [ ] 加入完整錯誤處理
   - [ ] 效能優化（減少重繪）

2. **功能增強**（3小時內）
   - [ ] 實作「新聞數字」爬蟲（PTT熱門文章）
   - [ ] 加入Excel匯出功能
   - [ ] 更豐富的統計圖表

3. **數據升級**（需確認）
   - [ ] 台彩官網爬蟲（需要討論合法性）
   - [ ] 建立歷史數據資料庫

4. **部署準備**（確認需求後）
   - [ ] GitHub Pages設定
   - [ ] 或自訂Domain + Hosting

---

**預估時間投入：**
- 優化現有代碼：2-4小時
- 新功能開發：8-12小時/功能
- 真實數據整合：20-30小時
- App轉換：40-60小時

---

## 📧 聯絡與授權

- 專案負責人：Jack
- 開發狀態：個人專案
- 授權方式：待定
- 商業化計畫：考慮中

---

**最後更新**：2025-01-21
**文檔版本**：v1.0
