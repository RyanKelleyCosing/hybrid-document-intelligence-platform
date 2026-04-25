export type ReviewField = {
  label: string;
  value: string;
};

export type ReviewItem = {
  id: string;
  sourceLabel: string;
  issuerLabel: string;
  profileLabel: string;
  fileName: string;
  receivedAt: string;
  averageConfidence: number;
  reasons: string[];
  fields: ReviewField[];
};

export const reviewItems: ReviewItem[] = [
  {
    id: "doc-1001",
    sourceLabel: "Azure SFTP drop",
    issuerLabel: "Bank",
    profileLabel: "Bank statement",
    fileName: "case-1001-statement.pdf",
    receivedAt: "Received 12 minutes ago",
    averageConfidence: 74,
    reasons: ["low confidence", "multiple account candidates"],
    fields: [
      { label: "Account candidate", value: "acct-1001 or acct-9102" },
      { label: "Document type", value: "Monthly statement" },
      { label: "Statement date", value: "Needs confirmation" },
    ],
  },
  {
    id: "doc-1002",
    sourceLabel: "Scanned upload",
    issuerLabel: "Collection agency",
    profileLabel: "Collection notice",
    fileName: "box-03-letter-annotated.jpg",
    receivedAt: "Received 31 minutes ago",
    averageConfidence: 69,
    reasons: ["missing required field"],
    fields: [
      { label: "Account number", value: "Not extracted" },
      { label: "Debtor name", value: "Jordan Patel" },
      { label: "Document type", value: "Collection letter" },
    ],
  },
  {
    id: "doc-1003",
    sourceLabel: "AWS S3 relay",
    issuerLabel: "Court",
    profileLabel: "Court filing",
    fileName: "batch-17-bill.pdf",
    receivedAt: "Received 54 minutes ago",
    averageConfidence: 78,
    reasons: ["low confidence"],
    fields: [
      { label: "Account number", value: "ACC-4041" },
      { label: "Amount due", value: "$1,248.33" },
      { label: "Cluster hint", value: "Case 17 packet" },
    ],
  },
];