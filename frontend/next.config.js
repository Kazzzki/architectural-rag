/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'standalone',
    transpilePackages: ['pdfjs-dist', 'react-pdf'],
    async rewrites() {
        return [
            {
                source: '/api/:path*',
                destination: process.env.API_URL || 'http://localhost:8000/api/:path*',
            },
        ];
    },
};

module.exports = nextConfig;
