import type { Metadata } from 'next';
import './globals.css';
import AuthProvider from './components/AuthProvider';

export const metadata: Metadata = {
    title: '建築意匠ナレッジベース',
    description: '建築PM/CM業務向けナレッジ検索・回答生成システム',
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="ja">
            <body>
                <AuthProvider>{children}</AuthProvider>
            </body>
        </html>
    );
}
