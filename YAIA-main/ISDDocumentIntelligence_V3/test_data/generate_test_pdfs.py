"""
Generate 50 employee PDF dossiers for Pinnacle Global Solutions Pvt. Ltd.
Each PDF contains personal details, group memberships, family relationships,
and activity participation -designed to test Document Intelligence + Connections Map.
"""

import os
from fpdf import FPDF

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "employees")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ORG_NAME = "Pinnacle Global Solutions Pvt. Ltd."
ORG_ADDRESS = "Tower B, 5th Floor, Manyata Tech Park, Hebbal, Bengaluru, Karnataka 560045"
ORG_PHONE = "+91-80-4567-8900"

GROUPS = {
    "Book Reading Club": {
        "coordinator": "Neha Sharma",
        "activities": [
            "Monthly Book Discussion -first Saturday of every month at the office library",
            "Annual Book Fair Visit -Bengaluru Book Festival, January 2026",
            "Author Meet -hosted Sudha Murthy for a talk on 15-Mar-2025",
            "Reading Challenge 2025 -each member pledged to read 24 books in the year",
            "Book Exchange Drive -quarterly exchange where members swap favourite reads",
        ],
    },
    "Sports Club": {
        "coordinator": "Vikram Patel",
        "activities": [
            "Inter-Department Cricket Tournament -held every quarter at Chinnaswamy grounds",
            "Badminton League -weekly doubles matches, Tuesday and Thursday evenings",
            "Annual Marathon Participation -Bengaluru 10K, October 2025",
            "Table Tennis Championship -office tournament held in August 2025",
            "Fitness Fridays -group yoga and stretching sessions every Friday 7:00 AM",
        ],
    },
    "Music & Arts Society": {
        "coordinator": "Divya Nair",
        "activities": [
            "Quarterly Cultural Evening -employees perform music, dance, drama",
            "Diwali Celebration 2025 -organized rangoli competition and musical night",
            "Guitar Workshop -8-week beginner course, instructor: Arjun Nair",
            "Annual Day Performance -choreographed group dance for company annual day",
            "Art Exhibition -displayed employee artwork in office lobby, Dec 2025",
        ],
    },
    "Community Service Group": {
        "coordinator": "Sunita Gupta",
        "activities": [
            "Blood Donation Camp -organized with Red Cross, 20-Jun-2025, 85 units collected",
            "Orphanage Visit -monthly visit to Sneha Orphanage, Whitefield",
            "Tree Plantation Drive -planted 500 saplings at Cubbon Park, Aug 2025",
            "Flood Relief Collection -raised Rs. 4,50,000 for North Karnataka flood victims",
            "Old Age Home Visit -quarterly visit to Sparsha Trust, Jayanagar",
        ],
    },
    "Tech Innovation Lab": {
        "coordinator": "Amit Sharma",
        "activities": [
            "Monthly Hackathon -24-hour coding sprints on the last Friday of each month",
            "Tech Talk Series -weekly lightning talks on emerging technologies",
            "AI/ML Study Group -bi-weekly deep dives into machine learning papers",
            "Open Source Contribution Drive -employees contributed to 12 OSS projects in 2025",
            "Internal Tool Development -built 'PinnaclBot' chatbot for HR queries",
        ],
    },
}

# --- Employee Data ---
# Family relationships are cross-referenced by employee ID
EMPLOYEES = [
    # === Kumar Family ===
    {
        "id": "EMP-001", "name": "Rajesh Kumar", "gender": "Male",
        "father": "Ramesh Kumar", "mother": "Savitri Devi",
        "dob": "15-Mar-1988", "nationality": "Indian", "religion": "Hindu",
        "height": "5'10\"", "blood_group": "B+",
        "phone": "+91-9845012301",
        "designation": "Senior Software Engineer", "department": "Engineering",
        "current_address": "Flat 402, Prestige Lakeside, Whitefield, Bengaluru 560066",
        "permanent_address": "H.No. 45, Sector 15, Chandigarh 160015",
        "groups": ["Sports Club", "Tech Innovation Lab"],
        "family_relations": [
            ("Suresh Kumar", "EMP-002", "Brother"),
            ("Priya Kumar", "EMP-015", "Wife"),
        ],
        "notes": "Team lead for the payment gateway migration project. Won 'Best Innovator' award in Q3 2025 hackathon. Plays opening batsman in the office cricket team. Owns a Honda City sedan, registration KA-01-MH-4521.",
    },
    {
        "id": "EMP-002", "name": "Suresh Kumar", "gender": "Male",
        "father": "Ramesh Kumar", "mother": "Savitri Devi",
        "dob": "22-Aug-1991", "nationality": "Indian", "religion": "Hindu",
        "height": "5'8\"", "blood_group": "B+",
        "phone": "+91-9845012302",
        "designation": "QA Engineer", "department": "Quality Assurance",
        "current_address": "Room 12, PG Lakshmi Nivas, Marathahalli, Bengaluru 560037",
        "permanent_address": "H.No. 45, Sector 15, Chandigarh 160015",
        "groups": ["Sports Club", "Community Service Group"],
        "family_relations": [
            ("Rajesh Kumar", "EMP-001", "Brother"),
        ],
        "notes": "Automation testing specialist. Volunteered for the blood donation camp and donated twice in 2025. Rides a Royal Enfield Classic 350, registration KA-03-EQ-7789.",
    },
    # === Sharma Family ===
    {
        "id": "EMP-003", "name": "Amit Sharma", "gender": "Male",
        "father": "Dinesh Sharma", "mother": "Kamla Sharma",
        "dob": "10-Jan-1985", "nationality": "Indian", "religion": "Hindu",
        "height": "5'11\"", "blood_group": "A+",
        "phone": "+91-9845012303",
        "designation": "Principal Architect", "department": "Engineering",
        "current_address": "Villa 18, Adarsh Palm Retreat, Bellandur, Bengaluru 560103",
        "permanent_address": "B-12, Adarsh Nagar, Jaipur, Rajasthan 302004",
        "groups": ["Tech Innovation Lab", "Book Reading Club"],
        "family_relations": [
            ("Neha Sharma", "EMP-004", "Sister"),
            ("Deepak Sharma", "EMP-020", "Cousin"),
        ],
        "notes": "Coordinates the Tech Innovation Lab. Architected the microservices migration. Published paper on distributed systems at IEEE conference. Drives a Hyundai Creta, registration KA-05-MJ-3345.",
    },
    {
        "id": "EMP-004", "name": "Neha Sharma", "gender": "Female",
        "father": "Dinesh Sharma", "mother": "Kamla Sharma",
        "dob": "05-Jul-1990", "nationality": "Indian", "religion": "Hindu",
        "height": "5'5\"", "blood_group": "A+",
        "phone": "+91-9845012304",
        "designation": "Product Manager", "department": "Product",
        "current_address": "Flat 305, Sobha Dream Acres, Panathur, Bengaluru 560103",
        "permanent_address": "B-12, Adarsh Nagar, Jaipur, Rajasthan 302004",
        "groups": ["Book Reading Club", "Music & Arts Society"],
        "family_relations": [
            ("Amit Sharma", "EMP-003", "Brother"),
            ("Deepak Sharma", "EMP-020", "Cousin"),
        ],
        "notes": "Coordinates the Book Reading Club. Led the launch of the mobile banking app v3.0. Organized the Sudha Murthy author meet event. Active classical dancer -performed Bharatanatyam at annual day.",
    },
    # === Patel Family ===
    {
        "id": "EMP-005", "name": "Vikram Patel", "gender": "Male",
        "father": "Jayesh Patel", "mother": "Hansa Patel",
        "dob": "18-Nov-1986", "nationality": "Indian", "religion": "Hindu",
        "height": "6'0\"", "blood_group": "O+",
        "phone": "+91-9845012305",
        "designation": "Engineering Manager", "department": "Engineering",
        "current_address": "Flat 601, Brigade Metropolis, Whitefield, Bengaluru 560066",
        "permanent_address": "23, Navrangpura, Ahmedabad, Gujarat 380009",
        "groups": ["Sports Club", "Tech Innovation Lab", "Community Service Group"],
        "family_relations": [
            ("Meera Patel", "EMP-006", "Wife"),
        ],
        "notes": "Coordinates the Sports Club. Captain of the office cricket team. Manages a team of 15 engineers. Led the cloud migration to AWS. Drives a Toyota Fortuner, registration KA-01-MN-9912. Organized the inter-department cricket tournament.",
    },
    {
        "id": "EMP-006", "name": "Meera Patel", "gender": "Female",
        "father": "Sunil Deshmukh", "mother": "Asha Deshmukh",
        "dob": "25-Feb-1989", "nationality": "Indian", "religion": "Hindu",
        "height": "5'4\"", "blood_group": "O-",
        "phone": "+91-9845012306",
        "designation": "UX Designer", "department": "Design",
        "current_address": "Flat 601, Brigade Metropolis, Whitefield, Bengaluru 560066",
        "permanent_address": "14, Model Colony, Pune, Maharashtra 411016",
        "groups": ["Music & Arts Society", "Book Reading Club"],
        "family_relations": [
            ("Vikram Patel", "EMP-005", "Husband"),
        ],
        "notes": "Redesigned the company's customer-facing portal. Won 'Best Design' award at internal UX summit. Painting hobbyist -exhibited 3 watercolors at the office Art Exhibition. Active in the Book Reading Club.",
    },
    # === Reddy Family ===
    {
        "id": "EMP-007", "name": "Srinivas Reddy", "gender": "Male",
        "father": "Venkata Reddy", "mother": "Sarojini Reddy",
        "dob": "30-Sep-1984", "nationality": "Indian", "religion": "Hindu",
        "height": "5'9\"", "blood_group": "AB+",
        "phone": "+91-9845012307",
        "designation": "Data Scientist", "department": "Data & Analytics",
        "current_address": "Flat 203, Salarpuria Sattva, Electronic City, Bengaluru 560100",
        "permanent_address": "Plot 67, Jubilee Hills, Hyderabad, Telangana 500033",
        "groups": ["Tech Innovation Lab", "Book Reading Club"],
        "family_relations": [
            ("Lakshmi Reddy", "EMP-008", "Sister"),
            ("Kiran Reddy", "EMP-025", "Cousin"),
        ],
        "notes": "Built the fraud detection ML model that saved Rs. 2.3 crore in Q2 2025. Presented at PyCon India 2025. Active in the AI/ML Study Group. Drives a Mahindra XUV700, registration KA-04-ED-2278.",
    },
    {
        "id": "EMP-008", "name": "Lakshmi Reddy", "gender": "Female",
        "father": "Venkata Reddy", "mother": "Sarojini Reddy",
        "dob": "14-Apr-1987", "nationality": "Indian", "religion": "Hindu",
        "height": "5'6\"", "blood_group": "AB+",
        "phone": "+91-9845012308",
        "designation": "HR Business Partner", "department": "Human Resources",
        "current_address": "Flat 105, Mantri Serenity, Kanakapura Road, Bengaluru 560062",
        "permanent_address": "Plot 67, Jubilee Hills, Hyderabad, Telangana 500033",
        "groups": ["Community Service Group", "Music & Arts Society"],
        "family_relations": [
            ("Srinivas Reddy", "EMP-007", "Brother"),
            ("Kiran Reddy", "EMP-025", "Cousin"),
        ],
        "notes": "Handles employee engagement and wellness programs. Organized the company's first Mental Health Awareness Week. Coordinated the flood relief fundraiser. Plays veena -performed at Diwali cultural evening.",
    },
    # === Gupta Family ===
    {
        "id": "EMP-009", "name": "Anand Gupta", "gender": "Male",
        "father": "Mohan Lal Gupta", "mother": "Pushpa Gupta",
        "dob": "08-Dec-1983", "nationality": "Indian", "religion": "Hindu",
        "height": "5'7\"", "blood_group": "A-",
        "phone": "+91-9845012309",
        "designation": "Finance Manager", "department": "Finance",
        "current_address": "Flat 802, Purva Fairmont, Old Airport Road, Bengaluru 560017",
        "permanent_address": "C-45, Civil Lines, Lucknow, Uttar Pradesh 226001",
        "groups": ["Book Reading Club", "Community Service Group"],
        "family_relations": [
            ("Sunita Gupta", "EMP-010", "Wife"),
        ],
        "notes": "Manages the annual budget of Rs. 150 crore. Led the cost optimization initiative saving 18% operational expenses. Active reader -completed 30 books in the 2025 Reading Challenge. Donated blood 4 times.",
    },
    {
        "id": "EMP-010", "name": "Sunita Gupta", "gender": "Female",
        "father": "Rakesh Verma", "mother": "Sushila Verma",
        "dob": "19-Jun-1986", "nationality": "Indian", "religion": "Hindu",
        "height": "5'3\"", "blood_group": "B+",
        "phone": "+91-9845012310",
        "designation": "CSR Lead", "department": "Corporate Social Responsibility",
        "current_address": "Flat 802, Purva Fairmont, Old Airport Road, Bengaluru 560017",
        "permanent_address": "D-22, Gomti Nagar, Lucknow, Uttar Pradesh 226010",
        "groups": ["Community Service Group", "Book Reading Club", "Music & Arts Society"],
        "family_relations": [
            ("Anand Gupta", "EMP-009", "Husband"),
        ],
        "notes": "Coordinates the Community Service Group. Organized blood donation camps collecting 85 units. Led the tree plantation drive at Cubbon Park. Sings Hindustani classical -performed at quarterly cultural evening.",
    },
    # === Nair Family ===
    {
        "id": "EMP-011", "name": "Arjun Nair", "gender": "Male",
        "father": "Krishnan Nair", "mother": "Radha Nair",
        "dob": "03-May-1992", "nationality": "Indian", "religion": "Hindu",
        "height": "5'10\"", "blood_group": "O+",
        "phone": "+91-9845012311",
        "designation": "DevOps Engineer", "department": "Infrastructure",
        "current_address": "Flat 504, Prestige Falcon City, Kanakapura Road, Bengaluru 560062",
        "permanent_address": "TC 14/321, Pattom, Thiruvananthapuram, Kerala 695004",
        "groups": ["Music & Arts Society", "Tech Innovation Lab"],
        "family_relations": [
            ("Divya Nair", "EMP-012", "Sister"),
        ],
        "notes": "Set up the company's CI/CD pipeline and Kubernetes infrastructure. Guitar instructor for the Music & Arts Society workshop. Plays rhythm guitar in the office band 'CodeStrings'. Rides a KTM Duke 390, registration KA-02-HH-5567.",
    },
    {
        "id": "EMP-012", "name": "Divya Nair", "gender": "Female",
        "father": "Krishnan Nair", "mother": "Radha Nair",
        "dob": "27-Oct-1994", "nationality": "Indian", "religion": "Hindu",
        "height": "5'5\"", "blood_group": "O+",
        "phone": "+91-9845012312",
        "designation": "Content Strategist", "department": "Marketing",
        "current_address": "Flat 201, Sobha Silicon Oasis, HSR Layout, Bengaluru 560102",
        "permanent_address": "TC 14/321, Pattom, Thiruvananthapuram, Kerala 695004",
        "groups": ["Music & Arts Society", "Book Reading Club", "Community Service Group"],
        "family_relations": [
            ("Arjun Nair", "EMP-011", "Brother"),
        ],
        "notes": "Coordinates the Music & Arts Society. Choreographed the annual day group dance. Writes the company newsletter. Trained Bharatanatyam dancer. Organized the orphanage visits at Sneha Orphanage.",
    },
    # === Singh Family ===
    {
        "id": "EMP-013", "name": "Harpreet Singh", "gender": "Male",
        "father": "Gurpreet Singh", "mother": "Jaswinder Kaur",
        "dob": "12-Jan-1990", "nationality": "Indian", "religion": "Sikh",
        "height": "6'1\"", "blood_group": "B+",
        "phone": "+91-9845012313",
        "designation": "Security Architect", "department": "InfoSec",
        "current_address": "Flat 703, Embassy Springs, Devanahalli, Bengaluru 562110",
        "permanent_address": "H.No. 89, Model Town, Ludhiana, Punjab 141002",
        "groups": ["Tech Innovation Lab", "Sports Club"],
        "family_relations": [
            ("Manpreet Singh", "EMP-014", "Brother"),
        ],
        "notes": "Designed the zero-trust security architecture. Certified CISSP and CEH. Led the company's first bug bounty program. Fast bowler in the cricket team. Drives a Jeep Compass, registration KA-01-MK-6634.",
    },
    {
        "id": "EMP-014", "name": "Manpreet Singh", "gender": "Male",
        "father": "Gurpreet Singh", "mother": "Jaswinder Kaur",
        "dob": "28-Sep-1993", "nationality": "Indian", "religion": "Sikh",
        "height": "5'11\"", "blood_group": "B-",
        "phone": "+91-9845012314",
        "designation": "Cloud Engineer", "department": "Infrastructure",
        "current_address": "Flat 704, Embassy Springs, Devanahalli, Bengaluru 562110",
        "permanent_address": "H.No. 89, Model Town, Ludhiana, Punjab 141002",
        "groups": ["Tech Innovation Lab", "Sports Club", "Community Service Group"],
        "family_relations": [
            ("Harpreet Singh", "EMP-013", "Brother"),
        ],
        "notes": "AWS Solutions Architect certified. Manages the company's multi-cloud infrastructure. Wicketkeeper in the cricket team. Organized the tree plantation drive logistics. Lives in the same apartment complex as his brother.",
    },
    # === Rajesh Kumar's wife ===
    {
        "id": "EMP-015", "name": "Priya Kumar", "gender": "Female",
        "father": "Mahesh Iyer", "mother": "Lakshmi Iyer",
        "dob": "20-Nov-1990", "nationality": "Indian", "religion": "Hindu",
        "height": "5'4\"", "blood_group": "A+",
        "phone": "+91-9845012315",
        "designation": "Business Analyst", "department": "Product",
        "current_address": "Flat 402, Prestige Lakeside, Whitefield, Bengaluru 560066",
        "permanent_address": "12, Mylapore, Chennai, Tamil Nadu 600004",
        "groups": ["Book Reading Club", "Community Service Group"],
        "family_relations": [
            ("Rajesh Kumar", "EMP-001", "Husband"),
            ("Suresh Kumar", "EMP-002", "Brother-in-law"),
        ],
        "notes": "Bridges business requirements and technical teams. Led the requirements gathering for the mobile app v3.0. Active in the orphanage visit program. Completed 28 books in the Reading Challenge 2025.",
    },
    # === Independent employees 16-19 ===
    {
        "id": "EMP-016", "name": "Farhan Ahmed", "gender": "Male",
        "father": "Imran Ahmed", "mother": "Fatima Ahmed",
        "dob": "07-Mar-1991", "nationality": "Indian", "religion": "Muslim",
        "height": "5'9\"", "blood_group": "O+",
        "phone": "+91-9845012316",
        "designation": "Full Stack Developer", "department": "Engineering",
        "current_address": "Flat 310, Rainbow Drive, Sarjapur Road, Bengaluru 560035",
        "permanent_address": "15/3, Banjara Hills, Hyderabad, Telangana 500034",
        "groups": ["Tech Innovation Lab", "Sports Club"],
        "family_relations": [],
        "notes": "Built the real-time notification system. Won 2nd place in the Q1 hackathon. All-rounder in the cricket team. Mentors junior developers in React and Node.js.",
    },
    {
        "id": "EMP-017", "name": "Sneha Krishnamurthy", "gender": "Female",
        "father": "Raghavendra Krishnamurthy", "mother": "Vasanthi Krishnamurthy",
        "dob": "16-Aug-1993", "nationality": "Indian", "religion": "Hindu",
        "height": "5'6\"", "blood_group": "A+",
        "phone": "+91-9845012317",
        "designation": "Machine Learning Engineer", "department": "Data & Analytics",
        "current_address": "Flat 108, Godrej Platinum, Tumkur Road, Bengaluru 560073",
        "permanent_address": "34, Basavanagudi, Bengaluru, Karnataka 560004",
        "groups": ["Tech Innovation Lab", "Book Reading Club"],
        "family_relations": [],
        "notes": "Developed the recommendation engine using collaborative filtering. Co-authored the fraud detection model with Srinivas Reddy. Presented at Women in Tech Summit 2025. Local Bengalurean.",
    },
    {
        "id": "EMP-018", "name": "Rohit Menon", "gender": "Male",
        "father": "Gopalan Menon", "mother": "Sujatha Menon",
        "dob": "01-Dec-1988", "nationality": "Indian", "religion": "Hindu",
        "height": "5'8\"", "blood_group": "B+",
        "phone": "+91-9845012318",
        "designation": "Scrum Master", "department": "Project Management",
        "current_address": "Flat 412, Mantri Pinnacle, Bannerghatta Road, Bengaluru 560076",
        "permanent_address": "MG Road, Ernakulam, Kochi, Kerala 682011",
        "groups": ["Sports Club", "Music & Arts Society"],
        "family_relations": [],
        "notes": "Certified SAFe Agilist. Manages 3 scrum teams across time zones. Badminton doubles champion 2025. Plays bass guitar in office band 'CodeStrings' with Arjun Nair.",
    },
    {
        "id": "EMP-019", "name": "Tanvi Bhatt", "gender": "Female",
        "father": "Sudhir Bhatt", "mother": "Nirmala Bhatt",
        "dob": "24-Apr-1995", "nationality": "Indian", "religion": "Hindu",
        "height": "5'3\"", "blood_group": "O-",
        "phone": "+91-9845012319",
        "designation": "Junior Developer", "department": "Engineering",
        "current_address": "PG Sunflower, Koramangala 4th Block, Bengaluru 560034",
        "permanent_address": "A-7, Satellite Area, Ahmedabad, Gujarat 380015",
        "groups": ["Tech Innovation Lab", "Music & Arts Society", "Community Service Group"],
        "family_relations": [],
        "notes": "Newest member of the engineering team, joined June 2025. Built the internal PinnaclBot chatbot for HR queries. Kathak dancer -performed solo at Diwali celebration. Active in old age home visits.",
    },
    # === Sharma cousin ===
    {
        "id": "EMP-020", "name": "Deepak Sharma", "gender": "Male",
        "father": "Suresh Sharma", "mother": "Geeta Sharma",
        "dob": "11-Feb-1989", "nationality": "Indian", "religion": "Hindu",
        "height": "5'10\"", "blood_group": "A+",
        "phone": "+91-9845012320",
        "designation": "Database Administrator", "department": "Infrastructure",
        "current_address": "Flat 209, Prestige Shantiniketan, Whitefield, Bengaluru 560048",
        "permanent_address": "C-8, Adarsh Nagar, Jaipur, Rajasthan 302004",
        "groups": ["Tech Innovation Lab", "Sports Club"],
        "family_relations": [
            ("Amit Sharma", "EMP-003", "Cousin"),
            ("Neha Sharma", "EMP-004", "Cousin"),
        ],
        "notes": "Manages all production databases (PostgreSQL, MongoDB, Redis). Optimized query performance reducing latency by 40%. Cousin of Amit and Neha Sharma -all from Jaipur. Wicketkeeper in cricket team alongside Manpreet Singh.",
    },
    # === Independent employees 21-24 ===
    {
        "id": "EMP-021", "name": "Ritu Saxena", "gender": "Female",
        "father": "Alok Saxena", "mother": "Meenakshi Saxena",
        "dob": "09-Sep-1992", "nationality": "Indian", "religion": "Hindu",
        "height": "5'5\"", "blood_group": "B+",
        "phone": "+91-9845012321",
        "designation": "Legal Counsel", "department": "Legal",
        "current_address": "Flat 506, Purva Riviera, Marathahalli, Bengaluru 560037",
        "permanent_address": "56, Hazratganj, Lucknow, Uttar Pradesh 226001",
        "groups": ["Book Reading Club", "Community Service Group"],
        "family_relations": [],
        "notes": "Handles all compliance and contract reviews. Drafted the company's data privacy policy. Active in the flood relief fundraiser -coordinated legal documentation. Avid reader of legal thrillers.",
    },
    {
        "id": "EMP-022", "name": "Mohammed Rizwan", "gender": "Male",
        "father": "Abdul Kareem", "mother": "Zainab Begum",
        "dob": "13-Jun-1987", "nationality": "Indian", "religion": "Muslim",
        "height": "5'11\"", "blood_group": "O+",
        "phone": "+91-9845012322",
        "designation": "Solutions Consultant", "department": "Pre-Sales",
        "current_address": "Flat 301, Salarpuria Greenage, Hosur Road, Bengaluru 560068",
        "permanent_address": "22/1, Frazer Town, Bengaluru, Karnataka 560005",
        "groups": ["Sports Club", "Book Reading Club"],
        "family_relations": [],
        "notes": "Won 'Top Deal Closer' for FY2025 with Rs. 45 crore in new contracts. Played university-level cricket for Bengaluru University. Opening bowler in the office cricket team. Local Bengalurean from Frazer Town.",
    },
    {
        "id": "EMP-023", "name": "Anjali Menon", "gender": "Female",
        "father": "Vijayan Menon", "mother": "Geetha Menon",
        "dob": "21-Jul-1994", "nationality": "Indian", "religion": "Hindu",
        "height": "5'4\"", "blood_group": "A-",
        "phone": "+91-9845012323",
        "designation": "UI Developer", "department": "Engineering",
        "current_address": "Flat 104, Brigade Gateway, Rajajinagar, Bengaluru 560055",
        "permanent_address": "Kaloor, Ernakulam, Kochi, Kerala 682017",
        "groups": ["Music & Arts Society", "Tech Innovation Lab"],
        "family_relations": [],
        "notes": "Built the responsive design system used across all company products. Created the rangoli competition designs for Diwali 2025. Frontend specialist in React and TypeScript. Mohiniyattam dancer.",
    },
    {
        "id": "EMP-024", "name": "Venkatesh Iyer", "gender": "Male",
        "father": "Srinivasan Iyer", "mother": "Alamelu Iyer",
        "dob": "02-Oct-1986", "nationality": "Indian", "religion": "Hindu",
        "height": "5'7\"", "blood_group": "B-",
        "phone": "+91-9845012324",
        "designation": "Technical Writer", "department": "Documentation",
        "current_address": "Flat 209, Prestige Ozone, Whitefield, Bengaluru 560066",
        "permanent_address": "15, T. Nagar, Chennai, Tamil Nadu 600017",
        "groups": ["Book Reading Club", "Tech Innovation Lab"],
        "family_relations": [],
        "notes": "Authors all API documentation and developer guides. Wrote the company's technical blog that gets 50K monthly views. Completed all 24 books in the Reading Challenge. Tamil poet -published 2 collections.",
    },
    # === Reddy cousin ===
    {
        "id": "EMP-025", "name": "Kiran Reddy", "gender": "Male",
        "father": "Narasimha Reddy", "mother": "Padmavathi Reddy",
        "dob": "17-May-1990", "nationality": "Indian", "religion": "Hindu",
        "height": "5'9\"", "blood_group": "AB+",
        "phone": "+91-9845012325",
        "designation": "Backend Developer", "department": "Engineering",
        "current_address": "Flat 410, Prestige Elysian, Bannerghatta Road, Bengaluru 560076",
        "permanent_address": "Plot 70, Jubilee Hills, Hyderabad, Telangana 500033",
        "groups": ["Tech Innovation Lab", "Sports Club"],
        "family_relations": [
            ("Srinivas Reddy", "EMP-007", "Cousin"),
            ("Lakshmi Reddy", "EMP-008", "Cousin"),
        ],
        "notes": "Developed the core payment processing engine. Cousin of Srinivas and Lakshmi Reddy -family from Jubilee Hills, Hyderabad. Table tennis champion 2025. Contributed to 5 open source projects.",
    },
    # === Independent employees 26-29 ===
    {
        "id": "EMP-026", "name": "Poornima Hegde", "gender": "Female",
        "father": "Raghunath Hegde", "mother": "Saraswathi Hegde",
        "dob": "06-Mar-1993", "nationality": "Indian", "religion": "Hindu",
        "height": "5'5\"", "blood_group": "O+",
        "phone": "+91-9845012326",
        "designation": "Graphic Designer", "department": "Design",
        "current_address": "Flat 302, Adarsh Residency, JP Nagar, Bengaluru 560078",
        "permanent_address": "Kadri Hills, Mangaluru, Karnataka 575004",
        "groups": ["Music & Arts Society", "Community Service Group"],
        "family_relations": [],
        "notes": "Designed the company's new brand identity and logo refresh. Created all posters for the community service events. Exhibited 5 digital art pieces at the office Art Exhibition. From Mangaluru, Karnataka.",
    },
    {
        "id": "EMP-027", "name": "Siddharth Jain", "gender": "Male",
        "father": "Praveen Jain", "mother": "Sunita Jain",
        "dob": "29-Aug-1988", "nationality": "Indian", "religion": "Jain",
        "height": "5'8\"", "blood_group": "A+",
        "phone": "+91-9845012327",
        "designation": "Account Manager", "department": "Sales",
        "current_address": "Flat 605, Mantri Espana, Bellandur, Bengaluru 560103",
        "permanent_address": "MI Road, Jaipur, Rajasthan 302001",
        "groups": ["Sports Club", "Book Reading Club"],
        "family_relations": [],
        "notes": "Manages the company's top 10 enterprise accounts worth Rs. 200 crore annually. Badminton singles finalist 2025. From Jaipur like the Sharma family -knows Amit Sharma from college.",
    },
    {
        "id": "EMP-028", "name": "Lavanya Subramaniam", "gender": "Female",
        "father": "Subramaniam K.", "mother": "Meenakshi Subramaniam",
        "dob": "15-Jan-1991", "nationality": "Indian", "religion": "Hindu",
        "height": "5'4\"", "blood_group": "B+",
        "phone": "+91-9845012328",
        "designation": "Data Engineer", "department": "Data & Analytics",
        "current_address": "Flat 108, Purva Venezia, Yelahanka, Bengaluru 560064",
        "permanent_address": "18, Anna Nagar, Madurai, Tamil Nadu 625020",
        "groups": ["Tech Innovation Lab", "Music & Arts Society"],
        "family_relations": [],
        "notes": "Built the company's data lake on AWS S3 + Glue. Works closely with Srinivas Reddy on the analytics pipeline. Carnatic vocalist -performed at quarterly cultural evening. Data pipeline processes 2TB daily.",
    },
    {
        "id": "EMP-029", "name": "Gaurav Thakur", "gender": "Male",
        "father": "Bhagat Singh Thakur", "mother": "Sarla Thakur",
        "dob": "04-Nov-1985", "nationality": "Indian", "religion": "Hindu",
        "height": "6'0\"", "blood_group": "O-",
        "phone": "+91-9845012329",
        "designation": "VP Operations", "department": "Operations",
        "current_address": "Villa 7, Total Environment, Whitefield, Bengaluru 560066",
        "permanent_address": "The Mall, Shimla, Himachal Pradesh 171001",
        "groups": ["Sports Club", "Community Service Group", "Book Reading Club"],
        "family_relations": [],
        "notes": "Oversees company operations across 3 offices (Bengaluru, Hyderabad, Pune). Marathon runner -completed the Bengaluru 10K in 48 minutes. Led the flood relief collection raising Rs. 4,50,000. Drives a BMW X3, registration KA-01-MR-1100.",
    },
    # === Joshi Family ===
    {
        "id": "EMP-030", "name": "Rahul Joshi", "gender": "Male",
        "father": "Prakash Joshi", "mother": "Anuradha Joshi",
        "dob": "23-Jun-1987", "nationality": "Indian", "religion": "Hindu",
        "height": "5'10\"", "blood_group": "A+",
        "phone": "+91-9845012330",
        "designation": "Mobile Developer", "department": "Engineering",
        "current_address": "Flat 501, Prestige Kew Gardens, Yeswanthpur, Bengaluru 560022",
        "permanent_address": "Deccan Gymkhana, Pune, Maharashtra 411004",
        "groups": ["Tech Innovation Lab", "Sports Club"],
        "family_relations": [
            ("Kavita Joshi", "EMP-031", "Wife"),
        ],
        "notes": "Lead mobile developer -built the iOS and Android apps. Won 'App of the Year' internal award. Fast bowler in the cricket team alongside Harpreet Singh. From Pune, Maharashtra.",
    },
    {
        "id": "EMP-031", "name": "Kavita Joshi", "gender": "Female",
        "father": "Ramdas Kulkarni", "mother": "Vaishali Kulkarni",
        "dob": "08-Sep-1989", "nationality": "Indian", "religion": "Hindu",
        "height": "5'5\"", "blood_group": "A-",
        "phone": "+91-9845012331",
        "designation": "Training Manager", "department": "Learning & Development",
        "current_address": "Flat 501, Prestige Kew Gardens, Yeswanthpur, Bengaluru 560022",
        "permanent_address": "Kothrud, Pune, Maharashtra 411038",
        "groups": ["Book Reading Club", "Community Service Group", "Music & Arts Society"],
        "family_relations": [
            ("Rahul Joshi", "EMP-030", "Husband"),
        ],
        "notes": "Designed the company's onboarding program and leadership development track. Organized 15 training workshops in 2025. Active in the old age home visits at Sparsha Trust. Plays harmonium at cultural events.",
    },
    # === Independent employees 32-39 ===
    {
        "id": "EMP-032", "name": "Aditya Kulkarni", "gender": "Male",
        "father": "Shrinivas Kulkarni", "mother": "Mangala Kulkarni",
        "dob": "19-Feb-1992", "nationality": "Indian", "religion": "Hindu",
        "height": "5'9\"", "blood_group": "B+",
        "phone": "+91-9845012332",
        "designation": "SRE Engineer", "department": "Infrastructure",
        "current_address": "Flat 203, Salarpuria Symphony, Sarjapur Road, Bengaluru 560035",
        "permanent_address": "Shivajinagar, Pune, Maharashtra 411005",
        "groups": ["Tech Innovation Lab", "Sports Club"],
        "family_relations": [],
        "notes": "Maintains 99.99% uptime for production systems. Implemented the observability stack (Grafana, Prometheus, Loki). Spin bowler in the cricket team. On-call rotation champion -resolved 45 incidents in 2025.",
    },
    {
        "id": "EMP-033", "name": "Nandini Rao", "gender": "Female",
        "father": "Shivakumar Rao", "mother": "Vijayalakshmi Rao",
        "dob": "11-Oct-1994", "nationality": "Indian", "religion": "Hindu",
        "height": "5'6\"", "blood_group": "O+",
        "phone": "+91-9845012333",
        "designation": "Marketing Manager", "department": "Marketing",
        "current_address": "Flat 304, Brigade Lakefront, Whitefield, Bengaluru 560066",
        "permanent_address": "Jayanagar, Bengaluru, Karnataka 560041",
        "groups": ["Book Reading Club", "Music & Arts Society"],
        "family_relations": [],
        "notes": "Grew the company's social media following by 300% in 2025. Launched the 'Pinnacle Stories' employer branding campaign. Local Bengalurean from Jayanagar. Plays flute -performed at Diwali celebration.",
    },
    {
        "id": "EMP-034", "name": "Prakash Hegde", "gender": "Male",
        "father": "Narayan Hegde", "mother": "Shanta Hegde",
        "dob": "26-Apr-1986", "nationality": "Indian", "religion": "Hindu",
        "height": "5'8\"", "blood_group": "AB-",
        "phone": "+91-9845012334",
        "designation": "Test Automation Lead", "department": "Quality Assurance",
        "current_address": "Flat 107, Sobha Indraprastha, Rajajinagar, Bengaluru 560010",
        "permanent_address": "Car Street, Udupi, Karnataka 576101",
        "groups": ["Tech Innovation Lab", "Community Service Group"],
        "family_relations": [],
        "notes": "Built the end-to-end test automation framework using Selenium and Playwright. Reduced regression testing time from 8 hours to 45 minutes. Active in the tree plantation drive. From Udupi, Karnataka.",
    },
    {
        "id": "EMP-035", "name": "Ishita Sen", "gender": "Female",
        "father": "Arijit Sen", "mother": "Rupa Sen",
        "dob": "31-Dec-1993", "nationality": "Indian", "religion": "Hindu",
        "height": "5'3\"", "blood_group": "B-",
        "phone": "+91-9845012335",
        "designation": "Customer Success Manager", "department": "Customer Success",
        "current_address": "Flat 405, Phoenix One, Indiranagar, Bengaluru 560038",
        "permanent_address": "Salt Lake, Kolkata, West Bengal 700091",
        "groups": ["Book Reading Club", "Community Service Group", "Music & Arts Society"],
        "family_relations": [],
        "notes": "Manages relationships with 25 enterprise customers. Achieved 96% customer retention rate. From Kolkata -organized Durga Puja celebration in office. Rabindra Sangeet singer at cultural evenings.",
    },
    {
        "id": "EMP-036", "name": "Varun Malhotra", "gender": "Male",
        "father": "Ashok Malhotra", "mother": "Reena Malhotra",
        "dob": "14-Jul-1990", "nationality": "Indian", "religion": "Hindu",
        "height": "5'10\"", "blood_group": "O+",
        "phone": "+91-9845012336",
        "designation": "Product Designer", "department": "Design",
        "current_address": "Flat 602, Nitesh Park Avenue, Whitefield, Bengaluru 560066",
        "permanent_address": "Greater Kailash, New Delhi 110048",
        "groups": ["Music & Arts Society", "Sports Club"],
        "family_relations": [],
        "notes": "Designed the company's design system 'Pinnacle UI'. Works closely with Meera Patel and Anjali Menon on the design team. Photographer -shot all company event photos. Table tennis runner-up 2025.",
    },
    {
        "id": "EMP-037", "name": "Ramya Bhat", "gender": "Female",
        "father": "Ganesh Bhat", "mother": "Suma Bhat",
        "dob": "03-Mar-1991", "nationality": "Indian", "religion": "Hindu",
        "height": "5'5\"", "blood_group": "A+",
        "phone": "+91-9845012337",
        "designation": "Payroll Specialist", "department": "Finance",
        "current_address": "Flat 201, Prestige Ferns Residency, HAL, Bengaluru 560008",
        "permanent_address": "Hampankatta, Mangaluru, Karnataka 575001",
        "groups": ["Community Service Group", "Book Reading Club"],
        "family_relations": [],
        "notes": "Processes monthly payroll for 500+ employees. Implemented the automated tax computation system. Active in the blood donation camp -coordinated logistics. Fellow Mangalurean with Poornima Hegde.",
    },
    {
        "id": "EMP-038", "name": "Nitin Bose", "gender": "Male",
        "father": "Subhash Bose", "mother": "Mira Bose",
        "dob": "18-May-1988", "nationality": "Indian", "religion": "Hindu",
        "height": "5'7\"", "blood_group": "B+",
        "phone": "+91-9845012338",
        "designation": "Procurement Manager", "department": "Operations",
        "current_address": "Flat 310, Adarsh Palm Retreat, Bellandur, Bengaluru 560103",
        "permanent_address": "Park Street, Kolkata, West Bengal 700016",
        "groups": ["Sports Club", "Book Reading Club"],
        "family_relations": [],
        "notes": "Manages vendor relationships and procurement for IT infrastructure. Negotiated contracts saving Rs. 2 crore annually. From Kolkata like Ishita Sen -they organize Bengali cultural events together. Badminton enthusiast.",
    },
    {
        "id": "EMP-039", "name": "Shruti Pandey", "gender": "Female",
        "father": "Rajendra Pandey", "mother": "Usha Pandey",
        "dob": "22-Aug-1995", "nationality": "Indian", "religion": "Hindu",
        "height": "5'4\"", "blood_group": "O-",
        "phone": "+91-9845012339",
        "designation": "Frontend Developer", "department": "Engineering",
        "current_address": "PG Comfort Stay, HSR Layout, Bengaluru 560102",
        "permanent_address": "Gomti Nagar, Lucknow, Uttar Pradesh 226010",
        "groups": ["Tech Innovation Lab", "Music & Arts Society"],
        "family_relations": [],
        "notes": "Built the real-time dashboard using React and D3.js. Youngest hackathon winner -won Q2 2025 hackathon. From Lucknow -same hometown as Sunita Gupta's family. Kathak performer at annual day.",
    },
    # === Rao Family ===
    {
        "id": "EMP-040", "name": "Venkatesh Rao", "gender": "Male",
        "father": "Narayana Rao", "mother": "Sarada Rao",
        "dob": "10-Jan-1984", "nationality": "Indian", "religion": "Hindu",
        "height": "5'11\"", "blood_group": "A+",
        "phone": "+91-9845012340",
        "designation": "CTO", "department": "Executive",
        "current_address": "Villa 12, Total Environment, Whitefield, Bengaluru 560066",
        "permanent_address": "Banjara Hills, Hyderabad, Telangana 500034",
        "groups": ["Tech Innovation Lab", "Book Reading Club", "Sports Club"],
        "family_relations": [
            ("Padma Rao", "EMP-041", "Sister"),
        ],
        "notes": "Chief Technology Officer. 20 years industry experience. Oversees all technology strategy. Lives in the same community as Gaurav Thakur (Total Environment, Whitefield). Marathon runner -ran Bengaluru 10K with Gaurav. Drives a Mercedes GLC, registration KA-01-MA-0007.",
    },
    {
        "id": "EMP-041", "name": "Padma Rao", "gender": "Female",
        "father": "Narayana Rao", "mother": "Sarada Rao",
        "dob": "25-Jun-1988", "nationality": "Indian", "religion": "Hindu",
        "height": "5'5\"", "blood_group": "A+",
        "phone": "+91-9845012341",
        "designation": "Talent Acquisition Lead", "department": "Human Resources",
        "current_address": "Flat 701, Brigade Caladium, Sahakar Nagar, Bengaluru 560092",
        "permanent_address": "Banjara Hills, Hyderabad, Telangana 500034",
        "groups": ["Community Service Group", "Music & Arts Society"],
        "family_relations": [
            ("Venkatesh Rao", "EMP-040", "Brother"),
        ],
        "notes": "Hired 120 employees in 2025 with a 92% offer acceptance rate. Works closely with Lakshmi Reddy on employee programs. Sister of CTO Venkatesh Rao. Organized the company's first 'Bring Your Pet to Work' day.",
    },
    # === Independent employees 42-44 ===
    {
        "id": "EMP-042", "name": "Joseph Thomas", "gender": "Male",
        "father": "Thomas Mathew", "mother": "Mary Thomas",
        "dob": "07-Sep-1989", "nationality": "Indian", "religion": "Christian",
        "height": "5'9\"", "blood_group": "O+",
        "phone": "+91-9845012342",
        "designation": "Network Engineer", "department": "Infrastructure",
        "current_address": "Flat 204, Prestige Ferns Galaxy, Bellandur, Bengaluru 560103",
        "permanent_address": "MG Road, Kottayam, Kerala 686001",
        "groups": ["Tech Innovation Lab", "Community Service Group"],
        "family_relations": [],
        "notes": "Manages the company's network across all offices. Set up the SD-WAN connecting Bengaluru, Hyderabad, and Pune offices. Active in the Sneha Orphanage visits. Certified CCNP. From Kottayam, Kerala.",
    },
    {
        "id": "EMP-043", "name": "Geeta Rawat", "gender": "Female",
        "father": "Mohan Singh Rawat", "mother": "Kamla Rawat",
        "dob": "30-Nov-1992", "nationality": "Indian", "religion": "Hindu",
        "height": "5'6\"", "blood_group": "B+",
        "phone": "+91-9845012343",
        "designation": "Admin Manager", "department": "Administration",
        "current_address": "Flat 103, Prestige Lakeside, Whitefield, Bengaluru 560066",
        "permanent_address": "Rajpur Road, Dehradun, Uttarakhand 248001",
        "groups": ["Community Service Group", "Sports Club"],
        "family_relations": [],
        "notes": "Manages office facilities across 3 floors. Organized logistics for all company events in 2025. Lives in the same apartment complex (Prestige Lakeside) as Rajesh and Priya Kumar. Fitness Fridays regular.",
    },
    {
        "id": "EMP-044", "name": "Arun Shetty", "gender": "Male",
        "father": "Devadas Shetty", "mother": "Jayanthi Shetty",
        "dob": "16-Apr-1987", "nationality": "Indian", "religion": "Hindu",
        "height": "5'8\"", "blood_group": "A-",
        "phone": "+91-9845012344",
        "designation": "iOS Developer", "department": "Engineering",
        "current_address": "Flat 405, Adarsh Palm Retreat, Bellandur, Bengaluru 560103",
        "permanent_address": "Bunder Road, Mangaluru, Karnataka 575001",
        "groups": ["Tech Innovation Lab", "Music & Arts Society"],
        "family_relations": [],
        "notes": "Built the iOS app with Rahul Joshi. Implemented SwiftUI migration. Third Mangalurean in the company along with Poornima Hegde and Ramya Bhat. Plays drums in office band 'CodeStrings'.",
    },
    # === Desai Family ===
    {
        "id": "EMP-045", "name": "Nikhil Desai", "gender": "Male",
        "father": "Ketan Desai", "mother": "Bharti Desai",
        "dob": "20-Jul-1988", "nationality": "Indian", "religion": "Hindu",
        "height": "5'10\"", "blood_group": "O+",
        "phone": "+91-9845012345",
        "designation": "Delivery Head", "department": "Delivery",
        "current_address": "Flat 901, Sobha Dream Acres, Panathur, Bengaluru 560103",
        "permanent_address": "CG Road, Ahmedabad, Gujarat 380006",
        "groups": ["Sports Club", "Book Reading Club", "Community Service Group"],
        "family_relations": [
            ("Pooja Desai", "EMP-046", "Wife"),
        ],
        "notes": "Manages delivery of 8 client projects worth Rs. 75 crore. From Ahmedabad like Vikram Patel -childhood friends. Marathon runner with Gaurav Thakur and Venkatesh Rao. Drives an Audi Q5, registration KA-01-MS-3321.",
    },
    {
        "id": "EMP-046", "name": "Pooja Desai", "gender": "Female",
        "father": "Hemant Shah", "mother": "Nilam Shah",
        "dob": "05-Feb-1991", "nationality": "Indian", "religion": "Hindu",
        "height": "5'3\"", "blood_group": "O-",
        "phone": "+91-9845012346",
        "designation": "Quality Lead", "department": "Quality Assurance",
        "current_address": "Flat 901, Sobha Dream Acres, Panathur, Bengaluru 560103",
        "permanent_address": "Navrangpura, Ahmedabad, Gujarat 380009",
        "groups": ["Book Reading Club", "Music & Arts Society"],
        "family_relations": [
            ("Nikhil Desai", "EMP-045", "Husband"),
        ],
        "notes": "Leads the manual testing team of 10. Implemented the accessibility testing framework. Wife of Nikhil Desai. Gujarati folk dancer -performed Garba at Diwali celebration. From Ahmedabad, Gujarat.",
    },
    # === Independent employees 47-50 ===
    {
        "id": "EMP-047", "name": "Sanjay Patil", "gender": "Male",
        "father": "Balaji Patil", "mother": "Sunanda Patil",
        "dob": "13-Dec-1986", "nationality": "Indian", "religion": "Hindu",
        "height": "5'9\"", "blood_group": "B+",
        "phone": "+91-9845012347",
        "designation": "Release Manager", "department": "Engineering",
        "current_address": "Flat 306, Purva Westend, Kudlu Gate, Bengaluru 560068",
        "permanent_address": "Shivaji Park, Mumbai, Maharashtra 400028",
        "groups": ["Tech Innovation Lab", "Sports Club"],
        "family_relations": [],
        "notes": "Manages bi-weekly production releases. Reduced deployment failures by 80% through automated pipelines. From Mumbai. Cricket team's vice-captain under Vikram Patel. Drives a Tata Harrier, registration KA-03-EF-4456.",
    },
    {
        "id": "EMP-048", "name": "Meghna Das", "gender": "Female",
        "father": "Tapan Das", "mother": "Chitrangada Das",
        "dob": "09-May-1994", "nationality": "Indian", "religion": "Hindu",
        "height": "5'4\"", "blood_group": "A+",
        "phone": "+91-9845012348",
        "designation": "BI Analyst", "department": "Data & Analytics",
        "current_address": "Flat 502, Salarpuria Sattva, Electronic City, Bengaluru 560100",
        "permanent_address": "Guwahati, Assam 781001",
        "groups": ["Book Reading Club", "Community Service Group"],
        "family_relations": [],
        "notes": "Creates executive dashboards and business intelligence reports. Works with Srinivas Reddy's data team. Lives in the same apartment complex as Srinivas Reddy (Salarpuria Sattva). From Guwahati, Assam. Active in flood relief coordination.",
    },
    {
        "id": "EMP-049", "name": "Pradeep Nambiar", "gender": "Male",
        "father": "Gopalakrishnan Nambiar", "mother": "Latha Nambiar",
        "dob": "28-Jan-1987", "nationality": "Indian", "religion": "Hindu",
        "height": "5'11\"", "blood_group": "O-",
        "phone": "+91-9845012349",
        "designation": "Compliance Officer", "department": "Legal",
        "current_address": "Flat 404, Brigade Lakefront, Whitefield, Bengaluru 560066",
        "permanent_address": "Palakkad, Kerala 678001",
        "groups": ["Book Reading Club", "Sports Club"],
        "family_relations": [],
        "notes": "Ensures regulatory compliance across all operations. Works with Ritu Saxena on legal matters. Fourth Keralite in the company after Arjun Nair, Divya Nair, and Rohit Menon. Badminton doubles partner of Rohit Menon.",
    },
    {
        "id": "EMP-050", "name": "Swati Deshpande", "gender": "Female",
        "father": "Vinayak Deshpande", "mother": "Madhavi Deshpande",
        "dob": "14-Jun-1993", "nationality": "Indian", "religion": "Hindu",
        "height": "5'5\"", "blood_group": "B-",
        "phone": "+91-9845012350",
        "designation": "Recruitment Specialist", "department": "Human Resources",
        "current_address": "Flat 206, Mantri Serenity, Kanakapura Road, Bengaluru 560062",
        "permanent_address": "Deccan Gymkhana, Pune, Maharashtra 411004",
        "groups": ["Music & Arts Society", "Community Service Group", "Book Reading Club"],
        "family_relations": [],
        "notes": "Recruited 60 engineers in 2025. Works closely with Padma Rao on talent strategy. From Pune like the Joshi family. Lives in the same apartment complex (Mantri Serenity) as Lakshmi Reddy. Active Lavani dancer.",
    },
]


def create_employee_pdf(emp: dict):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(11, 44, 74)
    pdf.cell(0, 10, ORG_NAME, new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, f"{ORG_ADDRESS} | {ORG_PHONE}", new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.ln(3)
    pdf.set_draw_color(11, 44, 74)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Document title
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(180, 30, 30)
    pdf.cell(0, 8, "EMPLOYEE PERSONNEL FILE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, f"Document ID: {emp['id']} | Classification: INTERNAL - CONFIDENTIAL", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    def section_header(title):
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(11, 44, 74)
        pdf.set_fill_color(230, 240, 250)
        pdf.cell(0, 7, f"  {title}", new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(2)

    def field(label, value):
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(55, 6, f"{label}:")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 6, str(value), new_x="LMARGIN", new_y="NEXT")

    # Personal Information
    section_header("PERSONAL INFORMATION")
    field("Full Name", emp["name"])
    field("Employee ID", emp["id"])
    field("Gender", emp["gender"])
    field("Date of Birth", emp["dob"])
    field("Father's Name", emp["father"])
    field("Mother's Name", emp["mother"])
    field("Nationality", emp["nationality"])
    field("Religion", emp["religion"])
    field("Height", emp["height"])
    field("Blood Group", emp["blood_group"])
    field("Phone", emp["phone"])
    pdf.ln(3)

    # Employment Details
    section_header("EMPLOYMENT DETAILS")
    field("Designation", emp["designation"])
    field("Department", emp["department"])
    field("Organization", ORG_NAME)
    field("Office Location", "Manyata Tech Park, Hebbal, Bengaluru")
    pdf.ln(3)

    # Addresses
    section_header("ADDRESS INFORMATION")
    field("Current Address", emp["current_address"])
    field("Permanent Address", emp["permanent_address"])
    pdf.ln(3)

    # Group Memberships
    section_header("GROUP MEMBERSHIPS & ACTIVITIES")
    for group_name in emp["groups"]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 6, f"  {group_name} (Coordinator: {GROUPS[group_name]['coordinator']})", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 80)
        for activity in GROUPS[group_name]["activities"]:
            pdf.cell(10, 5, "")
            pdf.cell(0, 5, f"- {activity}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    pdf.ln(2)

    # Family Relationships
    if emp["family_relations"]:
        section_header("FAMILY RELATIONSHIPS WITHIN ORGANIZATION")
        for rel_name, rel_id, rel_type in emp["family_relations"]:
            field(rel_type, f"{rel_name} ({rel_id})")
        pdf.ln(3)

    # Additional Notes
    section_header("ADDITIONAL NOTES & OBSERVATIONS")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 5, emp["notes"])
    pdf.ln(5)

    # Footer
    pdf.set_draw_color(11, 44, 74)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, f"This document is the property of {ORG_NAME}. For internal use only.", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 5, f"Generated for testing purposes. Employee ID: {emp['id']}", new_x="LMARGIN", new_y="NEXT", align="C")

    # Save
    safe_name = emp["name"].replace(" ", "_")
    filename = f"{emp['id']}_{safe_name}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)
    pdf.output(filepath)
    return filename


if __name__ == "__main__":
    print(f"Generating {len(EMPLOYEES)} employee PDFs...")
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    for i, emp in enumerate(EMPLOYEES):
        filename = create_employee_pdf(emp)
        print(f"  [{i+1:2d}/50] {filename}")

    print()
    print(f"Done! {len(EMPLOYEES)} PDFs generated in: {OUTPUT_DIR}")
    print()
    print("Cross-reference summary:")
    print("  - Kumar family: EMP-001, EMP-002, EMP-015 (brothers + wife)")
    print("  - Sharma family: EMP-003, EMP-004, EMP-020 (siblings + cousin)")
    print("  - Patel family: EMP-005, EMP-006 (husband + wife)")
    print("  - Reddy family: EMP-007, EMP-008, EMP-025 (siblings + cousin)")
    print("  - Gupta family: EMP-009, EMP-010 (husband + wife)")
    print("  - Nair family: EMP-011, EMP-012 (brother + sister)")
    print("  - Singh family: EMP-013, EMP-014 (brothers)")
    print("  - Joshi family: EMP-030, EMP-031 (husband + wife)")
    print("  - Rao family: EMP-040, EMP-041 (brother + sister)")
    print("  - Desai family: EMP-045, EMP-046 (husband + wife)")
    print()
    print("Shared locations:")
    print("  - Prestige Lakeside, Whitefield: EMP-001, EMP-015, EMP-043")
    print("  - Total Environment, Whitefield: EMP-029, EMP-040")
    print("  - Salarpuria Sattva, Electronic City: EMP-007, EMP-048")
    print("  - Mantri Serenity, Kanakapura Road: EMP-008, EMP-050")
    print("  - Sobha Dream Acres, Panathur: EMP-004, EMP-045, EMP-046")
