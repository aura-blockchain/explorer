import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
export default function TxSearch({ onSearch, result, error }) {
    const [value, setValue] = useState('');
    const [loading, setLoading] = useState(false);
    const handleSubmit = async (event) => {
        event.preventDefault();
        setLoading(true);
        try {
            await onSearch(value);
        }
        finally {
            setLoading(false);
        }
    };
    return (_jsxs("div", { className: "panel", children: [_jsx("h3", { children: "Search Blocks & Transactions" }), _jsxs("form", { className: "tx-search", onSubmit: handleSubmit, children: [_jsx("input", { value: value, onChange: (event) => setValue(event.target.value), placeholder: "Enter block height or Tx hash" }), _jsx("button", { type: "submit", disabled: loading, children: loading ? 'Searching…' : 'Search' })] }), error && _jsx("p", { style: { color: '#f87171', marginTop: '1rem' }, children: error }), result && (_jsxs("div", { className: "tx-result", children: [_jsx("strong", { children: result.type === 'block' ? 'Block' : 'Transaction' }), " @ height ", result.height, _jsx("br", {}), "Hash: ", result.hash] }))] }));
}
