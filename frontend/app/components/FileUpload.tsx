"use client";

import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';

const FileUpload = () => {
    const [uploading, setUploading] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [status, setStatus] = useState<'success' | 'error' | null>(null);

    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        if (acceptedFiles.length === 0) return;

        const file = acceptedFiles[0];
        setUploading(true);
        setMessage(`アップロード中: ${file.name}...`);
        setStatus(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const res = await fetch(`${API_BASE}/api/upload`, {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Upload failed');
            }

            const data = await res.json();
            setStatus('success');
            setStatus('success');
            setMessage(`アップロード完了: ${data.filename}`);
            // 3秒後に詳細メッセージを表示
            setTimeout(() => {
                setMessage(`ファイルは自動解析キューに追加されました。\n分類とOCR処理がバックグラウンドで進行中です。\nしばらくしてからリロードしてください。`);
            }, 1000);
        } catch (error: any) {
            console.error('Upload Error:', error);
            setStatus('error');
            setMessage(`アップロード失敗: ${error.message}`);
        } finally {
            setUploading(false);
        }
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: {
            'application/pdf': ['.pdf'],
            'image/png': ['.png'],
            'image/jpeg': ['.jpg', '.jpeg'],
        },
        multiple: false,
    });

    return (
        <div className="p-6 bg-white rounded-lg shadow-md mb-8">
            <h2 className="text-xl font-bold mb-4 text-gray-800">ファイルアップロード</h2>

            <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
                    }`}
            >
                <input {...getInputProps()} />
                {uploading ? (
                    <div>
                        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500 mx-auto mb-2"></div>
                        <p className="text-gray-600">アップロード中...</p>
                    </div>
                ) : (
                    <div>
                        <p className="text-lg text-gray-600 mb-2">
                            ここにファイルをドラッグ＆ドロップ
                        </p>
                        <p className="text-sm text-gray-400">
                            または、クリックしてファイルを選択 (.pdf, .png, .jpg)
                        </p>
                    </div>
                )}
            </div>

            {message && (
                <div className={`mt-4 p-4 rounded-lg ${status === 'success' ? 'bg-green-100 text-green-700' :
                    status === 'error' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                    }`}>
                    {message}
                </div>
            )}
        </div>
    );
};

export default FileUpload;
