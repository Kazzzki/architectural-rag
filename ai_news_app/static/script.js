document.addEventListener('DOMContentLoaded', () => {
    const fetchBtn = document.getElementById('fetchBtn');
    const forceRefreshBtn = document.getElementById('forceRefreshBtn');
    const emailBtn = document.getElementById('emailBtn');
    const newsGrid = document.getElementById('newsGrid');
    const statusMessage = document.getElementById('statusMessage');
    const metaInfo = document.getElementById('metaInfo');
    const lastUpdatedTime = document.getElementById('lastUpdatedTime');
    const loader = document.getElementById('loader');
    const loaderText = document.getElementById('loaderText');
    const tabBtns = document.querySelectorAll('.tab-btn');

    let currentArticles = [];
    let currentCategory = 'All';

    // Initial load: Try to get cached news quietly
    fetchNews(false, true);

    fetchBtn.addEventListener('click', () => {
        fetchNews(false);
    });

    forceRefreshBtn.addEventListener('click', () => {
        if (confirm("最新のニュースを取得・翻訳しなおします（数分かかります）。よろしいですか？")) {
            fetchNews(true);
        }
    });

    async function fetchNews(force = false, quiet = false) {
        if (!quiet) showLoader(force ? '最新ニュースを取得・翻訳中（数分かかります）...' : 'ニュースを読み込み中...');
        setStatus('');

        try {
            // Append ?force=true if needed
            const url = force ? '/api/fetch?force=true' : '/api/fetch';
            const response = await fetch(url, { method: 'POST' });
            const data = await response.json();

            if (data.status === 'success') {
                currentArticles = data.articles;

                if (data.last_updated) {
                    lastUpdatedTime.textContent = data.last_updated;
                    metaInfo.classList.remove('hidden');
                }

                if (currentArticles.length > 0) {
                    filterAndRender();
                    emailBtn.disabled = false;
                    setStatus(
                        force
                            ? `${currentArticles.length}件のニュースを取得・更新しました`
                            : `${currentArticles.length}件のニュースを表示しました`
                        , 'success'
                    );
                } else {
                    // If no articles yet (start up), maybe still updating
                    if (data.is_updating) {
                        setStatus('バックグラウンドで集計中です。しばらくしてから「最新ニュースを表示」を押してください。', 'success');
                    } else {
                        setStatus('ニュースがまだありません。「強制更新」を試してください。');
                    }
                }

            } else {
                setStatus('エラーが発生しました: ' + data.message, 'error');
            }
        } catch (error) {
            setStatus('通信エラーが発生しました', 'error');
            console.error(error);
        } finally {
            if (!quiet) hideLoader();
        }
    }

    emailBtn.addEventListener('click', async () => {
        if (currentArticles.length === 0) return;

        showLoader('メールを送信中...');
        setStatus('');

        try {
            const response = await fetch('/api/send-email', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ articles: currentArticles })
            });
            const data = await response.json();

            if (data.status === 'success') {
                setStatus('全記事のメールを送信しました！', 'success');
            } else {
                setStatus('メール送信エラー: ' + data.message, 'error');
            }
        } catch (error) {
            setStatus('通信エラーが発生しました', 'error');
        } finally {
            hideLoader();
        }
    });

    // Tab Filtering Logic
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Update UI
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update Filter
            currentCategory = btn.getAttribute('data-category');
            filterAndRender();
        });
    });

    function filterAndRender() {
        if (currentArticles.length === 0) {
            newsGrid.innerHTML = '<div class="empty-state"><p>ニュースを読み込んでいます...</p></div>';
            return;
        }

        let filtered = currentArticles;
        if (currentCategory !== 'All') {
            filtered = currentArticles.filter(a => a.category === currentCategory);
        }

        renderNews(filtered);
    }

    function renderNews(articles) {
        newsGrid.innerHTML = '';

        if (articles.length === 0) {
            newsGrid.innerHTML = '<div class="empty-state"><p>このカテゴリの記事は見つかりませんでした。</p></div>';
            return;
        }

        articles.forEach((article, index) => {
            const card = document.createElement('div');
            card.className = 'news-card';
            card.style.animationDelay = `${index * 0.05}s`;

            card.innerHTML = `
                <div class="card-category">${article.category}</div>
                <h3><a href="${article.link}" target="_blank">${article.title}</a></h3>
                <div class="news-meta">
                    <span class="meta-item">
                        <span class="meta-icon">🌐</span> ${article.source}
                    </span>
                    <span class="meta-item">
                        <span class="meta-icon">📅</span> ${article.published}
                    </span>
                </div>
                <div class="news-summary">
                    ${article.summary}
                </div>
            `;
            newsGrid.appendChild(card);
        });
    }

    function showLoader(text) {
        loaderText.textContent = text;
        loader.classList.remove('hidden');
    }

    function hideLoader() {
        loader.classList.add('hidden');
    }

    function setStatus(msg, type) {
        statusMessage.textContent = msg;
        statusMessage.className = 'status-message';
        if (type) statusMessage.classList.add(`status-${type}`);
    }
});
