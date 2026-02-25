#!/bin/bash
while true; do
    echo "--- Starting new batch of 5 ---"
    python3 run_batch.py > /tmp/batch_output.log 2>&1
    INDEXED=$(grep "'indexed': " /tmp/batch_output.log | awk -F"'indexed': " '{print $2}' | awk -F"," '{print $1}')
    cat /tmp/batch_output.log | grep -v 'HTTP Request: POST' | grep -v 'FutureWarning' | grep -v 'NotOpenSSLWarning' | tail -n 10
    if [ "$INDEXED" = "0" ]; then
        echo "All PDFs processed!"
        break
    fi
    sleep 3
done
