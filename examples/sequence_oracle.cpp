// Exact Held-Karp reference for a directed cyclic setup-cost matrix.
// Benchmark-only C++17 helper. It never executes model-generated code.
#include <algorithm>
#include <iostream>
#include <limits>
#include <vector>

int main() {
    int n;
    if (!(std::cin >> n) || n < 3 || n > 20) return 2;
    std::vector<int> costs(n * n);
    for (int& value : costs) if (!(std::cin >> value) || value < 0 || value > 1000000) return 2;
    const int m = n - 1, states = 1 << m;
    const long long inf = std::numeric_limits<long long>::max() / 4;
    std::vector<long long> dp(static_cast<size_t>(states) * m, inf);
    std::vector<int> parent(static_cast<size_t>(states) * m, -1);
    for (int j = 0; j < m; ++j) dp[(1 << j) * m + j] = costs[j + 1];
    for (int mask = 1; mask < states; ++mask) {
        for (int j = 0; j < m; ++j) if (mask & (1 << j)) {
            int previous = mask ^ (1 << j);
            if (!previous) continue;
            for (int k = 0; k < m; ++k) if (previous & (1 << k)) {
                long long candidate = dp[previous * m + k] + costs[(k + 1) * n + j + 1];
                if (candidate < dp[mask * m + j]) {
                    dp[mask * m + j] = candidate;
                    parent[mask * m + j] = k;
                }
            }
        }
    }
    long long best = inf;
    int last = -1, mask = states - 1;
    for (int j = 0; j < m; ++j) {
        long long value = dp[mask * m + j] + costs[(j + 1) * n];
        if (value < best) { best = value; last = j; }
    }
    std::vector<int> order;
    while (last >= 0) {
        order.push_back(last + 1);
        int next = parent[mask * m + last];
        mask ^= 1 << last;
        last = next;
    }
    std::reverse(order.begin(), order.end());
    std::cout << best << '\n' << 0;
    for (int job : order) std::cout << ' ' << job;
    std::cout << '\n';
}
