import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export default function BlocksTable({ blocks }) {
    if (!blocks.length) {
        return _jsx("p", { children: "No blocks yet. Ensure the local validators are running via docker-compose.testnet." });
    }
    return (_jsxs("table", { className: "blocks-table", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Height" }), _jsx("th", { children: "Time" }), _jsx("th", { children: "Txs" }), _jsx("th", { children: "Proposer" }), _jsx("th", { children: "Hash" })] }) }), _jsx("tbody", { children: blocks.map((block) => (_jsxs("tr", { children: [_jsxs("td", { children: ["#", block.height.toLocaleString()] }), _jsx("td", { children: new Date(block.time).toLocaleTimeString() }), _jsx("td", { children: block.txs }), _jsxs("td", { children: [block.proposer.slice(0, 12), "\u2026"] }), _jsxs("td", { children: [block.hash.slice(0, 12), "\u2026"] })] }, block.height))) })] }));
}
