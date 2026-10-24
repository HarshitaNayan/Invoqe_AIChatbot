# Python collections
A list is an ordered mutable collection. A tuple is ordered and immutable. A dictionary maps unique keys to values. A set stores unique elements and is useful for membership tests. Mutability means an object can change after creation. Example: items = [1, 2]; items.append(3).

# Recursion and base cases
A recursive function calls itself on a smaller version of a problem. A base case stops the recursion. For factorial, factorial(0) = 1 and factorial(n) = n * factorial(n-1) for positive integers. Recursion uses stack frames and can reach Python's recursion-depth limit.

# NumPy arrays and shapes
A NumPy array has a dtype and a shape. Shape (2, 3) means two rows and three columns. reshape changes the shape while keeping the same number of elements. astype returns an array converted to a requested dtype. concatenate joins existing axes, while stack creates a new axis. searchsorted returns insertion indices for an array assumed to be sorted.

# Pandas data cleaning
A DataFrame is a table with labelled rows and columns. Inspect data with head, info, describe and isna. Check missing data and duplicates before choosing a cleaning method. Fit preprocessing only on training data to avoid leakage into evaluation. Do not drop records without understanding why values are missing.

# Train, validation and test data
Training data fits a model. Validation data or cross-validation compares models and hyperparameters. A final test set estimates performance after choices are locked. In time series, earlier observations should precede later test observations. Accuracy is a classification measure; MAE and RMSE measure regression error. R-squared is not percentage accuracy.

# Retrieval and embeddings
TF-IDF weighs words by their frequency within a document and rarity across the corpus. Cosine similarity compares vector directions. Latent semantic analysis uses truncated singular value decomposition of a document-term matrix to create dense embeddings. These embeddings depend on corpus co-occurrence patterns and are not equivalent to pretrained neural semantic embeddings. Retrieval provides selected reference text to a language model; it does not guarantee factual answers.

# SQL and parameterized queries
SQL selects and modifies relational data. A primary key identifies a row. A foreign key links tables. Parameterized queries pass values separately from SQL text and help prevent SQL injection. Passwords should be salted and hashed using a password-specific derivation function rather than stored in plaintext.

# HTTP and APIs
HTTP requests have methods, paths, headers and sometimes bodies. GET retrieves a resource and POST typically submits data. A 200 response means a request was handled successfully; it does not prove an AI answer is correct. A 401 response indicates missing or invalid authentication. A 429 response indicates rate limiting. Secret API keys belong on the server, not in public source code.
