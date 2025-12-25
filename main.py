    def search(self, original_query):
        print("\n" + "="*30)
        print(f"🚀 מתחיל חיפוש עבור: {original_query}")
        
        smart_keywords = self._enhance_query(original_query)
        print(f"🔍 מילות מפתח מתורגמות: {smart_keywords}")

        params = {
            'app_key': APP_KEY,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5',
            'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot',
            'format': 'json',
            'v': '2.0',
            'keywords': smart_keywords,
            'target_currency': 'ILS',
            'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC',
            'page_size': '50',
        }
        params['sign'] = generate_sign(params)
        
        try:
            print("⏳ שולח בקשה לאליאקספרס...")
            # הדפסת ה-URL המלא לבדיקה
            # print(f"DEBUG URL Request: https://api-sg.aliexpress.com/sync with params: {params}")
            
            resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
            
            # --- כאן הבדיקה הקריטית ---
            # אם יש שגיאה, אליאקספרס מחזיר שדה בשם error_response
            if 'error_response' in resp:
                print(f"❌ שגיאה קריטית מה-API: {resp['error_response']}")
                return []
            
            print("✅ התקבלה תשובה מהשרת. מעבד נתונים...")
            
            data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
            
            # בדיקה אם בכלל חזרו מוצרים
            if not data:
                print(f"⚠️ ה-API החזיר תשובה תקינה אך ריקה ממוצרים! התשובה הגולמית: {resp}")
                return []

            products_raw = data.get('products', {}).get('product', [])
            
            if not products_raw:
                print("⚠️ רשימת המוצרים ריקה (products list is empty).")
                return []
            
            if isinstance(products_raw, dict): products_raw = [products_raw]

            print(f"📦 נמצאו {len(products_raw)} מוצרים גולמיים. מתחיל סינון...")

            parsed_products = []
            for i, p in enumerate(products_raw):
                try:
                    # מנסה לחלץ נתונים, אם נכשל מדפיס למה
                    sales = int(p.get('last_volume', 0))
                    rate_str = str(p.get('evaluate_rate', '0')).replace('%', '')
                    rating = float(rate_str) / 20 if rate_str else 0.0
                    
                    # הדפסת דוגמה למוצר הראשון והשני כדי לראות שהכל תקין
                    if i < 2:
                        print(f"   🔎 בודק מוצר: {p.get('product_title')[:20]}... | מכירות: {sales} | דירוג: {rating}")

                    parsed_products.append({
                        "title": p['product_title'],
                        "price": p.get('target_sale_price', 'N/A'),
                        "image": p.get('product_main_image_url'),
                        "raw_url": p.get('product_detail_url', ''),
                        "rating": round(rating, 1),
                        "sales": sales
                    })
                except Exception as e:
                    print(f"   ⚠️ שגיאה בעיבוד מוצר ספציפי: {e}")
                    continue

            # לוגיקת המדרג
            premium = [p for p in parsed_products if p['rating'] >= 4.7 and p['sales'] >= 10]
            if len(premium) >= 2:
                print(f"💎 נמצאו {len(premium)} מוצרי פרימיום!")
                premium.sort(key=lambda x: x['sales'], reverse=True)
                return premium[:4]
            
            good = [p for p in parsed_products if p['rating'] >= 4.5]
            if len(good) >= 1:
                print(f"👍 נמצאו {len(good)} מוצרים טובים.")
                good.sort(key=lambda x: x['sales'], reverse=True)
                return good[:4]
            
            print("📉 לא נמצאו מוצרים בדירוג גבוה, מחזיר את הנמכרים ביותר (Fallback).")
            parsed_products.sort(key=lambda x: x['sales'], reverse=True)
            return parsed_products[:4]

        except Exception as e:
            print(f"❌❌ קריסה כללית בחיפוש: {e}")
            return []
