
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(req: NextRequest) {
    // 環境変数から認証情報を取得
    // NEXT_PUBLIC_API_PASSWORD をそのまま流用 (user:password)
    const basicAuthCredentials = `user:${process.env.NEXT_PUBLIC_API_PASSWORD || ''}`;

    if (!process.env.NEXT_PUBLIC_API_PASSWORD) {
        // パスワード未設定の場合は認証スキップ（開発中など）
        return NextResponse.next();
    }

    const basicAuth = req.headers.get('authorization');

    if (basicAuth) {
        const authValue = basicAuth.split(' ')[1];
        const [user, pwd] = atob(authValue).split(':');

        // ユーザー名は任意、パスワードが一致すればOK
        if (pwd === process.env.NEXT_PUBLIC_API_PASSWORD) {
            return NextResponse.next();
        }
    }

    // 認証失敗またはヘッダーなし -> 401
    return new NextResponse('Authentication required', {
        status: 401,
        headers: {
            'WWW-Authenticate': 'Basic realm="Antigravity Secure Area"',
        },
    });
}

export const config = {
    matcher: [
        /*
         * Match all request paths except for the ones starting with:
         * - api (API routes) -> protected by backend
         * - _next/static (static files)
         * - _next/image (image optimization files)
         * - favicon.ico (favicon file)
         */
        '/((?!api|_next/static|_next/image|favicon.ico).*)',
    ],
};
